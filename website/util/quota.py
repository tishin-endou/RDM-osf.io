# -*- coding: utf-8 -*-
import logging

from addons.base import signals as file_signals
from addons.osfstorage.models import OsfStorageFileNode
from api.base import settings as api_settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Sum
from django.db.models.functions import Coalesce
from osf.models import AbstractNode, BaseFileNode, FileLog, FileInfo, Guid, OSFUser, UserQuota


def used_quota(user_id):
    guid = Guid.objects.get(
        _id=user_id,
        content_type_id=ContentType.objects.get_for_model(OSFUser).id
    )
    projects = AbstractNode.objects.filter(creator_id=guid.object_id).all()
    projects_ids = list(map(lambda p: p.id, projects))

    files = OsfStorageFileNode.objects.filter(
        target_object_id__in=projects_ids,
        target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
        deleted_on=None,
        deleted_by_id=None,
    ).all()
    files_ids = list(map(lambda f: f.id, files))

    db_sum = FileInfo.objects.filter(file_id__in=files_ids).aggregate(
        filesize_sum=Coalesce(Sum('file_size'), 0))
    return db_sum['filesize_sum']

def abbreviate_size(size):
    size = float(size)
    abbr_dict = {0: 'B', 1: 'KB', 2: 'MB', 3: 'GB', 4: 'TB'}

    power = 0
    while size > 1024 and power < 4:
        size /= 1024
        power += 1

    return (size, abbr_dict[power])

@file_signals.file_updated.connect
def update_used_quota(self, target, user, event_type, payload):
    try:
        file_node = BaseFileNode.objects.get(
            _id=payload['metadata']['path'].strip('/'),
            target_object_id=target.id,
            target_content_type_id=ContentType.objects.get_for_model(AbstractNode),
        )
    except BaseFileNode.DoesNotExist:
        logging.error('FileNode not found, cannot update used quota!')
        return

    if event_type == FileLog.FILE_ADDED:
        file_added(target, payload, file_node)
    elif event_type == FileLog.FILE_REMOVED:
        node_removed(target, user, payload, file_node)
    elif event_type == FileLog.FILE_UPDATED:
        file_modified(target, user, payload, file_node)

def file_added(target, payload, file_node):
    file_size = int(payload['metadata']['size'])
    if file_size < 0:
        return
    try:
        user_quota = UserQuota.objects.get(
            user=target.creator,
            storage_type=UserQuota.NII_STORAGE
        )
        user_quota.used += file_size
        user_quota.save()
    except UserQuota.DoesNotExist:
        UserQuota.objects.create(
            user=target.creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=file_size
        )

    FileInfo.objects.create(file=file_node, file_size=file_size)

def node_removed(target, user, payload, file_node):
    user_quota = UserQuota.objects.filter(
        user=target.creator,
        storage_type=UserQuota.NII_STORAGE
    ).first()
    if user_quota is not None:
        if 'osf.trashed' not in file_node.type:
            logging.error('FileNode is not trashed, cannot update used quota!')
            return

        for removed_file in get_node_file_list(file_node):
            try:
                file_info = FileInfo.objects.get(file=removed_file)
            except FileInfo.DoesNotExist:
                logging.error('FileInfo not found, cannot update used quota!')
                continue

            file_size = min(file_info.file_size, user_quota.used)
            user_quota.used -= file_size
        user_quota.save()

def file_modified(target, user, payload, file_node):
    file_size = int(payload['metadata']['size'])
    if file_size < 0:
        return

    user_quota, _ = UserQuota.objects.get_or_create(
        user=target.creator,
        storage_type=UserQuota.NII_STORAGE,
        defaults={'max_quota': api_settings.DEFAULT_MAX_QUOTA}
    )

    try:
        file_info = FileInfo.objects.get(file=file_node)
    except FileInfo.DoesNotExist:
        file_info = FileInfo(file=file_node, file_size=0)

    user_quota.used += file_size - file_info.file_size
    if user_quota.used < 0:
        user_quota.used = 0
    user_quota.save()

    file_info.file_size = file_size
    file_info.save()

def get_node_file_list(file_node):
    if 'file' in file_node.type:
        return [file_node]

    file_list = []
    folder_list = [file_node]

    while len(folder_list) > 0:
        folder_id_list = list(map(lambda f: f.id, folder_list))
        folder_list = []
        for child_file_node in BaseFileNode.objects.filter(parent_id__in=folder_id_list):
            if 'folder' in child_file_node.type:
                folder_list.append(child_file_node)
            else:  # file
                file_list.append(child_file_node)

    return file_list
