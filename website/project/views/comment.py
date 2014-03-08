# -*- coding: utf-8 -*-
import logging
import collections
import httplib as http

from framework import request
from framework.exceptions import HTTPError
from framework.auth.decorators import must_be_logged_in
from ..decorators import must_be_contributor_or_public

from website import settings
from website.filters import gravatar

from framework.forms.utils import sanitize
from website.models import Guid, Comment


logger = logging.getLogger(__name__)

def resolve_target(node, guid):

    if not guid:
        return node
    target = Guid.load(guid)
    if target is None:
        raise HTTPError(http.BAD_REQUEST)
    return target.referent


def collect_discussion(target, users=None, node=None, auth=None):

    # todo does node comment status matter? probably optimal to check that first before checking each comment
    
    is_contributor = True if auth and auth.user in node.contributors else False

    users = users or collections.defaultdict(list)
    for comment in getattr(target, 'commented', []):
        if not comment.is_deleted and (is_contributor or comment.is_public):
            users[comment.user].append(comment)

        collect_discussion(comment, users=users)
    return users


@must_be_contributor_or_public
def comment_discussion(**kwargs):
    node = kwargs['node'] or kwargs['project']
    auth = kwargs['auth'] if 'auth' in kwargs else None
    users = collect_discussion(node, node=node, auth=auth)
    # Sort users by comment frequency
    # TODO: Allow sorting by recency, combination of frequency and recency
    sorted_users = sorted(
        users.keys(),
        key=lambda item: len(users[item]),
        reverse=True,
    )
    return {
        'discussion': [
            {
                'id': user._id,
                'url': user.url,
                'fullname': user.fullname,
                'isContributor': node.is_contributor(user),
                'gravatarUrl': gravatar(
                    user, use_ssl=True,
                    size=settings.GRAVATAR_SIZE_DISCUSSION,
                ),

            }
            for user in sorted_users
        ]
    }


def serialize_comment(comment, auth):

    return {
        'id': comment._id,
        'author': {
            'id': comment.user._id,
            'url': comment.user.url,
            'name': comment.user.fullname,
        },
        'dateCreated': comment.date_created.strftime('%x %X'),
        'dateModified': comment.date_modified.strftime('%x %X'),
        'content': comment.content,
        'isPublic': 'public' if comment.is_public else 'private',
        'hasChildren': bool(getattr(comment, 'commented', [])),
        'canEdit': comment.user == auth.user,
        'modified': comment.modified,
        'isDeleted': comment.is_deleted,
        'isAbuse': auth.user and auth.user._id in comment.reports,
    }

def serialize_comments(record, node, auth):

    return [
        serialize_comment(comment, auth)
        for comment in getattr(record, 'commented', [])
        if comment.can_view(node, auth)
    ]


def kwargs_to_comment(kwargs, owner=False):

    comment = Comment.load(kwargs.get('cid'))
    if comment is None:
        raise HTTPError(http.BAD_REQUEST)

    if owner:
        auth = kwargs['auth']
        if auth.user != comment.user:
            raise HTTPError(http.FORBIDDEN)

    return comment


@must_be_logged_in
@must_be_contributor_or_public
def add_comment(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    if not node.comment_level:
        raise HTTPError(http.BAD_REQUEST)

    if not node.can_comment(auth):
        raise HTTPError(http.FORBIDDEN)

    guid = request.json.get('target')
    target = resolve_target(node, guid)

    content = request.json.get('content')
    if content is None:
        raise HTTPError(http.BAD_REQUEST)
    content = sanitize(content)

    is_public_string = request.json.get('isPublic')
    if is_public_string not in ['public', 'private']:
        raise HTTPError(http.BAD_REQUEST)
    is_public = is_public_string == 'public'

    comment = Comment.create(
        auth=auth,
        node=node,
        target=target,
        user=auth.user,
        is_public=is_public,
        content=content,
    )
    comment.save()

    return {
        'comment': serialize_comment(comment, auth)
   }, http.CREATED


@must_be_contributor_or_public
def list_comments(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    if not node.can_comment(auth):
        return {'comments': []}

    guid = request.args.get('target')
    target = resolve_target(node, guid)

    return {
        'comments': serialize_comments(target, node, auth),
    }


@must_be_logged_in
@must_be_contributor_or_public
def edit_comment(**kwargs):

    auth = kwargs['auth']
    node = kwargs['node'] or kwargs['project']

    comment = kwargs_to_comment(kwargs, owner=True)

    content = request.json.get('content')
    if content is None:
        raise HTTPError(http.BAD_REQUEST)

    is_public_string = request.json.get('isPublic')
    if is_public_string not in ['public', 'private']:
        raise HTTPError(http.BAD_REQUEST)
    is_public = is_public_string == 'public'

    comment.edit(
        content=sanitize(content),
        is_public=is_public,
        auth=auth,
        save=True
    )

    return serialize_comment(comment, auth)


@must_be_logged_in
@must_be_contributor_or_public
def delete_comment(**kwargs):

    auth = kwargs['auth']
    comment = kwargs_to_comment(kwargs, owner=True)
    comment.delete(auth=auth, save=True)

    return {}


@must_be_logged_in
@must_be_contributor_or_public
def undelete_comment(**kwargs):

    auth = kwargs['auth']
    comment = kwargs_to_comment(kwargs, owner=True)
    comment.undelete(auth=auth, save=True)

    return {}


@must_be_logged_in
@must_be_contributor_or_public
def report_abuse(**kwargs):

    auth = kwargs['auth']
    user = auth.user

    comment = kwargs_to_comment(kwargs)

    category = request.json.get('category')
    text = request.json.get('text', '')
    if not category:
        raise HTTPError(http.BAD_REQUEST)

    try:
        comment.report_abuse(user, save=True, category=category, text=text)
    except ValueError:
        raise HTTPError(http.BAD_REQUEST)

    return {}


@must_be_logged_in
@must_be_contributor_or_public
def unreport_abuse(**kwargs):

    auth = kwargs['auth']
    user = auth.user

    comment = kwargs_to_comment(kwargs)

    try:
        comment.unreport_abuse(user, save=True)
    except ValueError:
        raise HTTPError(http.BAD_REQUEST)

    return {}
