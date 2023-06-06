"""Views for the node settings page."""
# -*- coding: utf-8 -*-
from rest_framework import status as http_status
from datetime import datetime
import os
import logging
import json

from flask import request
from flask import redirect

from framework.auth.decorators import must_be_logged_in
from framework.exceptions import HTTPError
from framework.celery_tasks.handlers import enqueue_task
from framework.celery_tasks import app as celery_app

from addons.base import generic_views
from .apps import SHORT_NAME
from .serializer import WEKOSerializer
from . import settings as weko_settings
from osf.models.metaschema import RegistrationSchema
from osf.utils import permissions
from website.project.decorators import (
    must_have_addon, must_be_addon_authorizer,
    must_have_permission, must_not_be_registration,
    must_be_contributor_or_public,
)
from osf.models import AbstractNode

from website.util import rubeus, api_url_for
from website.oauth.utils import get_service
from website.oauth.signals import oauth_complete

from admin.rdm_addons.decorators import must_be_rdm_addons_allowed
from admin.rdm_addons.utils import get_rdm_addon_option
from addons.metadata import SHORT_NAME as METADATA_SHORT_NAME
from addons.metadata.packages import to_metadata_value
from .deposit import deposit_metadata


logger = logging.getLogger('addons.weko.views')


def _metadata_entry_is_empty(entry):
    if 'value' not in entry:
        return True
    value = entry['value']
    return value == ''

def _to_creators_json(users):
    return json.dumps([
        _to_user_json(user)
        for user in users
    ])

def _to_user_json(user):
    return {
        'number': user.erad,
        'name_ja': ''.join([user.family_name_ja, user.middle_names_ja, user.given_name_ja]),
        'name_en': ' '.join([user.given_name, user.middle_names, user.family_name]),
    }

def _get_repository_options(user_settings):
    repos = list(weko_settings.REPOSITORY_IDS)
    for institution_id in user_settings.owner.affiliated_institutions.all():
        rdm_addon_option = get_rdm_addon_option(institution_id, SHORT_NAME, create=False)
        if rdm_addon_option is None:
            continue
        for account in rdm_addon_option.external_accounts.all():
            display_name = account.display_name if '#' not in account.display_name else account.display_name[account.display_name.index('#') + 1:]
            repos.append({
                'id': account.provider_id,
                'name': display_name,
            })
    return repos

def _response_files_metadata(addon, files):
    return {
        'data': {
            'id': addon.owner._id,
            'type': 'metadata-node-files',
            'attributes': files,
        }
    }

def _response_file_metadata(addon, path, progress=None, result=None, error=None):
    attr = {
        'path': path,
    }
    if progress is not None:
        attr['progress'] = progress
    if result is not None:
        attr['result'] = result
    else:
        attr['progress_url'] = request.path
    if error is not None:
        attr['error'] = error
    return {
        'data': {
            'id': addon.owner._id,
            'type': 'weko-sword-result',
            'attributes': attr,
        }
    }

def _get_file_metadata_node(node, metadata_node_id):
    if node._id == metadata_node_id:
        return node
    nodes = [n for n in node.nodes if n._id == metadata_node_id]
    if len(nodes) == 0:
        raise ValueError('Unexpected node ID: {}'.format(metadata_node_id))
    return AbstractNode.objects.filter(guids___id=metadata_node_id).first()

@must_be_logged_in
@must_be_rdm_addons_allowed(SHORT_NAME)
def weko_oauth_connect(repoid, auth):
    service = get_service(SHORT_NAME)
    return redirect(service.get_repo_auth_url(repoid))

@must_be_logged_in
@must_be_rdm_addons_allowed(SHORT_NAME)
def weko_oauth_callback(repoid, auth):
    user = auth.user
    provider = get_service(SHORT_NAME)

    # Retrieve permanent credentials from provider
    if not provider.repo_auth_callback(user=user, repoid=repoid):
        return {}

    if provider.account and not user.external_accounts.filter(id=provider.account.id).exists():
        user.external_accounts.add(provider.account)
        user.save()

    oauth_complete.send(provider, account=provider.account, user=user)

    return {}


weko_account_list = generic_views.account_list(
    SHORT_NAME,
    WEKOSerializer
)

weko_import_auth = generic_views.import_auth(
    SHORT_NAME,
    WEKOSerializer
)

weko_deauthorize_node = generic_views.deauthorize_node(
    SHORT_NAME
)

weko_get_config = generic_views.get_config(
    SHORT_NAME,
    WEKOSerializer
)

## Auth ##

@must_be_logged_in
def weko_user_config_get(auth, **kwargs):
    """View for getting a JSON representation of the logged-in user's
    WEKO user settings.
    """

    user_addon = auth.user.get_addon('weko')
    user_has_auth = False
    if user_addon:
        user_has_auth = user_addon.has_auth

    return {
        'result': {
            'userHasAuth': user_has_auth,
            'urls': {
                'accounts': api_url_for('weko_account_list'),
            },
            'repositories': _get_repository_options(user_addon),
        },
    }, http_status.HTTP_200_OK


## Config ##

@must_not_be_registration
@must_have_addon(SHORT_NAME, 'user')
@must_have_addon(SHORT_NAME, 'node')
@must_be_addon_authorizer(SHORT_NAME)
@must_have_permission(permissions.WRITE)
def weko_set_config(node_addon, user_addon, auth, **kwargs):
    """Saves selected WEKO and Index to node settings"""

    user_settings = node_addon.user_settings
    user = auth.user

    if user_settings and user_settings.owner != user:
        raise HTTPError(http_status.HTTP_403_FORBIDDEN)

    index_id = request.json.get('index', {}).get('id')

    if index_id is None:
        return HTTPError(http_status.HTTP_400_BAD_REQUEST)

    c = node_addon.create_client()
    index = c.get_index_by_id(index_id)

    node_addon.set_folder(index, auth)

    return {'index': index.title}, http_status.HTTP_200_OK

## HGRID ##

@must_be_contributor_or_public
@must_have_addon(SHORT_NAME, 'node')
def weko_root_folder(node_addon, auth, **kwargs):
    # Quit if no indices linked
    if not node_addon.complete:
        return []
    return [rubeus.build_addon_root(
        node_addon,
        node_addon.index_title,
        permissions={'view': True, 'edit': True},
        private_key=kwargs.get('view_only', None),
    )]

@must_be_contributor_or_public
@must_have_addon(SHORT_NAME, 'node')
def weko_get_file_metadata(auth, **kwargs):
    node = kwargs['node'] or kwargs['project']
    addon = node.get_addon(SHORT_NAME)
    return _response_files_metadata(addon, [])

@must_be_logged_in
@must_have_permission('write')
@must_have_addon(SHORT_NAME, 'node')
@must_have_addon(METADATA_SHORT_NAME, 'node')
def weko_generate_draft_metadata(auth, did=None, index_id=None, mnode=None, filepath=None, **kwargs):
    node = kwargs['node'] or kwargs['project']
    mnode_obj = _get_file_metadata_node(node, mnode)
    metadata_addon = mnode_obj.get_addon(METADATA_SHORT_NAME)
    file_metadata = metadata_addon.get_file_metadata_for_path(filepath)
    _, filename = os.path.split(filepath)
    schema_id = RegistrationSchema.objects.get(name=weko_settings.REGISTRATION_SCHEMA_NAME)._id
    default_data = {
        'grdm-file:pubdate': to_metadata_value(datetime.now().date().isoformat()),
        'grdm-file:Title.ja': to_metadata_value(f'{filename} - {node.title}'),
        'grdm-file:Creator': to_metadata_value(_to_creators_json([auth.user])),
        'grdm-file:resourcetype': to_metadata_value('dataset'),
    }
    if file_metadata is None:
        file_metadata = {
            'path': filepath,
            'folder': False,
            'hash': '',
            'items': [
                {
                    'active': True,
                    'schema': schema_id,
                    'data': default_data,
                },
            ],
        }
    else:
        if 'items' not in file_metadata:
            file_metadata['items'] = []
        items = [i for i in file_metadata['items'] if i.get('schema', None) == schema_id]
        if len(items) == 0:
            file_metadata['items'].append({
                'active': True,
                'schema': schema_id,
                'data': default_data,
            })
        else:
            item = items[0]
            if 'data' not in item:
                item['data'] = {}
            for k, v in default_data.items():
                if k in item['data'] and not _metadata_entry_is_empty(item['data'][k]):
                    continue
                item['data'][k] = v
    metadata_addon.set_file_metadata(filepath, file_metadata)
    logger.info(f'Draft metadata {filepath}, {file_metadata}')
    return file_metadata

@must_be_logged_in
@must_have_permission('write')
@must_have_addon(SHORT_NAME, 'node')
@must_have_addon(METADATA_SHORT_NAME, 'node')
def weko_publish_file(auth, did=None, index_id=None, mnode=None, filepath=None, **kwargs):
    node = kwargs['node'] or kwargs['project']
    mnode_obj = _get_file_metadata_node(node, mnode)
    addon = node.get_addon(SHORT_NAME)
    metadata_addon = mnode_obj.get_addon(METADATA_SHORT_NAME)
    file_metadata_ = metadata_addon.get_file_metadata_for_path(filepath)
    if not addon.validate_index_id(index_id):
        logger.error(f'The index is not out of range: {index_id}')
        return HTTPError(http_status.HTTP_400_BAD_REQUEST)
    content_path = request.json.get('content_path', filepath) if request.json is not None else filepath
    after_delete_path = request.json.get('after_delete_path', None) if request.json is not None else None
    addon.set_publish_task_id(filepath, None)
    enqueue_task(deposit_metadata.s(
        auth.user._id, index_id, node._id, mnode_obj._id, file_metadata_, filepath, content_path, after_delete_path
    ))
    return _response_file_metadata(addon, filepath)

@must_be_logged_in
@must_have_permission('read')
@must_have_addon(SHORT_NAME, 'node')
@must_have_addon(METADATA_SHORT_NAME, 'node')
def weko_get_publishing_file(auth, did=None, index_id=None, mnode=None, filepath=None, **kwargs):
    node = kwargs['node'] or kwargs['project']
    addon = node.get_addon(SHORT_NAME)
    task_info = addon.get_publish_task_id(filepath)
    if task_info is None:
        return HTTPError(http_status.HTTP_404_NOT_FOUND)
    task_id = task_info['task_id']
    if task_id is None:
        return HTTPError(http_status.HTTP_404_NOT_FOUND)
    aresult = celery_app.AsyncResult(task_id)
    error = None
    progress = None
    result = None
    if aresult.failed():
        error = str(aresult.info)
    elif aresult.info is not None and 'progress' in aresult.info:
        progress = {
            'state': aresult.state,
            'rate': aresult.info['progress'],
        }
    elif aresult.info is not None and 'result' in aresult.info:
        result = aresult.info['result']
    return _response_file_metadata(addon, filepath, progress=progress, error=error, result=result)
