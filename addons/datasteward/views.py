"""Views for the add-on's user settings page."""
import asyncio
import logging
from itertools import islice

from bulk_update.helper import bulk_update
# -*- coding: utf-8 -*-
from django.apps import apps
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Max
from django.db.models.functions import Coalesce
from flask import request
from rest_framework import status as http_status

from framework.auth.decorators import must_be_logged_in
from osf.exceptions import UserStateError, ValidationValueError
from osf.models import Contributor
from osf.models.node import AbstractNode
from osf.models.nodelog import NodeLog
from osf.utils.permissions import ADMIN, READ
from website import language
from website.project import signals as project_signals
from timeit import default_timer as timer

logger = logging.getLogger(__name__)

SHORT_NAME = 'datasteward'
OSF_NODE = 'osf.node'
BATCH_SIZE = 1000


@must_be_logged_in
def datasteward_user_config_get(auth, **kwargs):
    """View for getting a JSON representation of DataSteward user settings"""
    user = auth.user
    addon_user_settings = user.get_addon(SHORT_NAME)
    addon_user_settings_enabled = addon_user_settings.enabled if addon_user_settings else False

    # If user is not a data steward and does not have add-on enabled before, return HTTP 403
    if not user.is_data_steward and not addon_user_settings_enabled:
        return {}, http_status.HTTP_403_FORBIDDEN

    return {
        'enabled': addon_user_settings_enabled,
    }, http_status.HTTP_200_OK


@must_be_logged_in
def datasteward_user_config_post(auth, **kwargs):
    """View for post DataSteward user settings with enabled value"""
    data = request.get_json()
    enabled = data.get('enabled', None)
    if enabled is None or not isinstance(enabled, bool):
        # If request's 'enabled' field is not valid, return HTTP 400
        return {}, http_status.HTTP_400_BAD_REQUEST

    user = auth.user
    # If user is not a DataSteward when enabling DataSteward add-on, return HTTP 403
    if not user.is_data_steward and enabled:
        return {}, http_status.HTTP_403_FORBIDDEN

    # Update add-on user settings
    addon_user_settings = user.get_addon(SHORT_NAME)
    addon_user_settings.enabled = enabled
    addon_user_settings.save()

    if enabled:
        # Enable DataSteward addon process
        enable_result = enable_datasteward_addon(auth)

        if not enable_result:
            return {}, http_status.HTTP_500_INTERNAL_SERVER_ERROR

        return {}, http_status.HTTP_200_OK
    else:
        # Disable DataSteward addon process
        skipped_projects = disable_datasteward_addon(auth)

        if skipped_projects is None:
            return {}, http_status.HTTP_500_INTERNAL_SERVER_ERROR

        response_body = {
            'skipped_projects': [
                {
                    'guid': project._id,
                    'name': project.title
                }
                for project in skipped_projects
            ]
        }

        return response_body, http_status.HTTP_200_OK


@transaction.atomic
def enable_datasteward_addon(auth, is_authenticating=False, **kwargs):
    """Start enable DataSteward add-on process"""
    # Check if user has any affiliated institutions
    affiliated_institutions = auth.user.affiliated_institutions.all()
    if not affiliated_institutions:
        return False
    try:
        user = auth.user.merged_by if auth.user.is_merged else auth.user

        projects = AbstractNode.objects.filter(type=OSF_NODE, affiliated_institutions__in=affiliated_institutions, is_deleted=False)
        contributors = Contributor.objects.filter(node__in=projects)

        add_contributor_list = []
        update_contributor_list = []
        update_permission_project_list = []
        for project in projects:
            related_contributors = contributors.filter(node=project)
            if related_contributors.filter(user=user).exists():
                contributor = related_contributors.first()

                # check if need to save old permission
                if not contributor.is_data_steward:
                    contributor.data_steward_old_permission = contributor.permission
                    contributor.is_data_steward = True
                    update_contributor_list.append(contributor)

                # check if need to update permission
                if contributor.permission != ADMIN:
                    update_permission_project_list.append(project)
            else:
                # add contributor
                kwargs = project.contributor_kwargs
                kwargs['_order'] = related_contributors.aggregate(**{'_order__max': Coalesce(Max('_order'), -1)}).get('_order__max') + 1
                new_contributor = Contributor(**kwargs)
                new_contributor.user = user
                new_contributor.is_data_steward = True
                new_contributor.visible = True
                add_contributor_list.append((project, new_contributor))

        # add contributor
        if add_contributor_list:
            if user.is_disabled:
                raise ValidationValueError('Deactivated users cannot be added as contributors.')

            if not user.is_registered and not user.unclaimed_records:
                raise UserStateError('This contributor cannot be added. If the problem persists please report it '
                                     'to ' + language.SUPPORT_LINK)

            new_contributors = [new_contributor for _, new_contributor in add_contributor_list]
            added_projects = [project for project, _ in add_contributor_list]
            bulk_create_contributors(new_contributors)

            # Bulk create NodeLog
            add_project_logs(added_projects, user, NodeLog.CONTRIB_ADDED)

            # send signal.
            loop = asyncio.new_event_loop()
            coroutines = [loop.create_task(add_contributor_permission(project=project, auth=auth)) for project, contributor in add_contributor_list]
            loop.run_until_complete(asyncio.wait(coroutines))
            loop.close()

        # save contributor's old permission
        if update_contributor_list:
            bulk_update(update_contributor_list, batch_size=BATCH_SIZE)

        # update contributor permission
        if update_permission_project_list:
            # set permission and send signal
            loop = asyncio.new_event_loop()
            coroutines = [loop.create_task(update_contributor_permission(project=project, auth=auth)) for project in update_permission_project_list]
            loop.run_until_complete(asyncio.wait(coroutines))
            loop.close()
    except Exception as e:
        # If error is raised while running on "Configure add-on accounts" screen, raise error
        # Otherwise, do nothing
        logger.error('Project {}: error raised while enabling DataSteward add-on with message "{}"'.format(project._id, e))
        if not is_authenticating:
            raise e
    return True


def bulk_create_contributors(contributors, batch_size=BATCH_SIZE):
    it = iter(contributors)
    while True:
        batch = list(islice(it, batch_size))
        if not batch:
            break
        Contributor.objects.bulk_create(batch, batch_size)


async def add_contributor_permission(project, auth):
    project.add_permission(auth.user, ADMIN, save=False)
    project_signals.contributors_updated.send(project)

    # enqueue on_node_updated/on_preprint_updated to update DOI metadata when a contributor is added
    if getattr(project, 'get_identifier_value', None) and project.get_identifier_value('doi'):
        project.update_or_enqueue_on_resource_updated(auth.user._id, first_save=False, saved_fields=['contributors'])


async def update_contributor_permission(project, auth, permission=ADMIN):
    if not project.get_group(permission).user_set.filter(id=auth.user.id).exists():
        project.set_permissions(auth.user, permission, save=False)
        permissions_changed = {
            auth.user._id: permission
        }
        params = project.log_params
        params['contributors'] = permissions_changed
        project.add_log(
            action=project.log_class.PERMISSIONS_UPDATED,
            params=params,
            auth=auth,
            save=False
        )
        if permission == READ:
            project_signals.write_permissions_revoked.send(project)

        project_signals.contributors_updated.send(project)


@transaction.atomic
def disable_datasteward_addon(auth):
    """Start disable DataSteward add-on process"""
    start = timer()
    # Check if user has any affiliated institutions
    affiliated_institutions = auth.user.affiliated_institutions.all()
    if not affiliated_institutions:
        return None

    user = auth.user
    skipped_projects = []

    projects = AbstractNode.objects.filter(type=OSF_NODE, affiliated_institutions__in=affiliated_institutions, is_deleted=False)

    # query admin group
    groups = Group.objects.filter(name__in=[project.format_group(ADMIN) for project in projects])

    # query admin contributors
    contributors = Contributor.objects.filter(node__in=projects, is_data_steward=True, user__is_active=True, user__groups__in=groups).distinct()
    local_contributors = list(contributors)

    # filter out project does not have user as contributor.
    project_id_list = contributors.filter(user=user).values_list('node__id', flat=True).distinct()
    if len(project_id_list) != projects.count():
        projects = projects.filter(id__in=project_id_list)

    update_permission_list = []
    bulk_update_contributors = []
    bulk_delete_contributor_id_list = []
    remove_permission_projects = []
    update_user = False
    start_prepare = timer()
    logger.info(f'disable_datasteward_addon before prepare runtime: {start_prepare - start}(s)')
    for project in projects:
        admin_contributors = [contributor for contributor in local_contributors if contributor.node.id == project.id]
        contributor = next((contributor for contributor in admin_contributors if contributor.user.id == user.id), None)
        if contributor is None:
            continue

        # can not be None
        if contributor.data_steward_old_permission is not None:
            if len(admin_contributors) <= 1:
                # has only one admin
                if ADMIN != contributor.data_steward_old_permission:
                    # if update to other permission than ADMIN then skip.
                    # else do nothing.
                    error_msg = '{} is the only admin.'.format(user.fullname)
                    logger.warning('Project {}: error raised while disabling DataSteward add-o with message "{}"'.format(project._id, error_msg))
                    skipped_projects.append(project)
            else:
                update_permission_list.append((project, contributor.data_steward_old_permission))
                contributor.is_data_steward = False
                contributor.data_steward_old_permission = None
                bulk_update_contributors.append(contributor)
        else:
            not_current_user_admins = [contributor for contributor in admin_contributors if contributor.user.id != user.id and contributor.visible is True]
            if not not_current_user_admins:
                # If user is the only visible contributor then skip
                logger.warning('Cannot remove user from project {}'.format(project._id))
                skipped_projects.append(project)
            else:
                # remove unclaimed record if necessary
                if project._id in user.unclaimed_records:
                    del user.unclaimed_records[project._id]
                    update_user = True
                bulk_delete_contributor_id_list.append(contributor.id)
                remove_permission_projects.append(project)

    start_update = timer()
    logger.info(f'disable_datasteward_addon prepare runtime: {start_update - start_prepare}(s)')
    # update contributor permission
    if update_permission_list:
        # set permission and send signal
        loop = asyncio.new_event_loop()
        coroutines = [loop.create_task(update_contributor_permission(project=project, auth=auth, permission=contributor_old_permission)) for
                      project, contributor_old_permission in update_permission_list]
        loop.run_until_complete(asyncio.wait(coroutines))
        loop.close()

        # update to DB
        bulk_update(bulk_update_contributors, update_fields=['is_data_steward', 'data_steward_old_permission'], batch_size=BATCH_SIZE)

    start_remove = timer()
    logger.info(f'disable_datasteward_addon update runtime: {start_remove - start_update}(s)')
    # remove contributor
    if remove_permission_projects:
        if update_user:
            # save after delete unclaimed_records
            user.save()

        # delete contributors
        Contributor.objects.filter(id__in=bulk_delete_contributor_id_list).delete()

        # clear permission and send signal
        clear_permissions(remove_permission_projects, user)

        add_project_logs(remove_permission_projects, user, NodeLog.CONTRIB_REMOVED)

        loop = asyncio.new_event_loop()
        coroutines = [loop.create_task(after_remove_contributor_permission(project=project, auth=auth)) for project in remove_permission_projects]
        loop.run_until_complete(asyncio.wait(coroutines))
        loop.close()

    end = timer()
    logger.info(f'disable_datasteward_addon remove runtime: {end - start_remove}(s)')
    logger.info(f'disable_datasteward_addon runtime: {end - start}(s)')
    return skipped_projects


def clear_permissions(projects, user):
    group_names = projects[0].groups.keys()
    project_group_names = [project.get_group(name) for name in group_names for project in projects]
    groups = user.groups.filter(name__in=project_group_names).distinct()

    if groups.exists():
        OSFUserGroup = apps.get_model('osf', 'osfuser_groups')
        OSFUserGroup.objects.filter(osfuser_id=user.id, group_id__in=[g.id for g in groups]).delete()


def add_project_logs(projects, user, action):
    logs = []
    for project in projects:
        params = project.log_params
        params['contributors'] = [user._id]
        params['node'] = params.get('node') or params.get('project') or project._id
        original_node = project if project._id == params['node'] else AbstractNode.load(params.get('node'))
        log = NodeLog(
            action=action, user=user, foreign_user=None,
            params=params, node=project, original_node=original_node
        )
        logs.append(log)

    it = iter(logs)
    while True:
        batch = list(islice(it, BATCH_SIZE))
        if not batch:
            break
        NodeLog.objects.bulk_create(batch, BATCH_SIZE)


async def after_remove_contributor_permission(project, auth):
    start_disconnect = timer()
    # After remove callback
    project.disconnect_addons(auth.user, auth)

    start_signals = timer()
    logger.info(f'disconnect_addons of project {project._id} runtime: {start_signals - start_disconnect}(s)')
    # send signal to remove this user from project subscriptions
    project_signals.contributor_removed.send(project, user=auth.user)
    project_signals.contributors_updated.send(project)

    start_enqueue = timer()
    logger.info(f'project_signals of project {project._id} runtime: {start_enqueue - start_signals}(s)')
    # enqueue on_node_updated/on_preprint_updated to update DOI metadata when a contributor is removed
    if getattr(project, 'get_identifier_value', None) and project.get_identifier_value('doi'):
        project.update_or_enqueue_on_resource_updated(auth.user._id, first_save=False, saved_fields=['contributors'])
    end_remove = timer()
    logger.info(f'update_or_enqueue_on_resource_updated of project {project._id} runtime: {end_remove - start_enqueue}(s)')
    logger.info(f'after_remove_contributor_permission of project {project._id} runtime: {end_remove - start_disconnect}(s)')
