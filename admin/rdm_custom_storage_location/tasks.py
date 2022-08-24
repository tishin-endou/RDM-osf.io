from __future__ import absolute_import

import requests
import json

from django.db import transaction
from api.base.utils import waterbutler_api_url_for
from celery.contrib.abortable import AbortableTask
from framework.celery_tasks import app as celery_app
from osf.models import ExportData, ExportDataLocation, ExportDataRestore
from addons.osfstorage.models import Region
from website.settings import WATERBUTLER_URL
from admin.rdm_custom_storage_location.export_data import serializers
from django.utils import timezone
import logging

__all__ = [
    'check_before_restore_export_data',
    'restore_export_data',
]

logger = logging.getLogger(__name__)
DATETIME_FORMAT = "%Y%m%dT%H%M%S"
EXPORT_FILE_PATH = "/export_{process_start}/export_data_{institution_guid}_{process_start}.json"
EXPORT_FILE_INFO_PATH = "/export_{process_start}/file_info_{institution_guid}_{process_start}.json"


@celery_app.task(bind=True, base=AbortableTask)
def check_before_restore_export_data(self, cookies, export_id, destination_id):
    # Try to add new process record to DB
    export_data_restore = ExportDataRestore(export_id=export_id, destination_id=destination_id, status="Running",
                                            process_start=timezone.now())
    export_data_restore.save()

    # Get export file (/export_{process_start}/export_data_{institution_guid}_{process_start}.json)
    export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
    export_base_url, export_settings, export_institution_guid = ExportDataLocation.objects.filter(id=export_data.location_id).values_list('waterbutler_url', 'waterbutler_settings', 'institution_guid')[0]
    export_provider = export_settings["storage"]["provider"]
    export_file_path = EXPORT_FILE_PATH.format(institution_guid=export_institution_guid,
                                               process_start=export_data.process_start.strftime(DATETIME_FORMAT))
    internal = export_base_url == WATERBUTLER_URL
    export_file_url = waterbutler_api_url_for('4h73y', export_provider, path=export_file_path, _internal=internal,
                                              meta="", base_url=export_base_url)
    try:
        response = requests.get(export_file_url,
                                headers={'content-type': 'application/json'},
                                cookies=cookies)
        if response.status_code != 200:
            # Error
            logger.error("Return error with response: {}".format(response.content))
            response.close()
            export_data_restore.status = "Stopped"
            export_data_restore.save()
            return "Cannot connect to the export data storage location"
    except Exception as e:
        logger.error("Exception: {}".format(e))
        response.close()
        export_data_restore.status = "Stopped"
        export_data_restore.save()
        return "Cannot connect to the export data storage location"

    response_body = response.json()
    response.close()

    # Validate export file
    schema = serializers.ExportDataSerializer(data=response_body)
    if not schema.is_valid():
        export_data_restore.status = "Stopped"
        export_data_restore.save()
        return "The export data files are corrupted"

    # Check whether the restore destination storage is not empty
    destination_region = Region.objects.filter(id=destination_id)
    destination_base_url, destination_guid, destination_settings = destination_region.values_list("waterbutler_url", "_id", "waterbutler_settings")[0]
    destination_provider = destination_settings["storage"]["provider"]
    internal = destination_base_url == WATERBUTLER_URL
    destination_storage_check_api = waterbutler_api_url_for(destination_id, destination_provider, path="/", meta="",
                                                            _internal=internal, base_url=destination_base_url)
    try:
        response = requests.head(destination_storage_check_api,
                                 headers={'content-type': 'application/json'},
                                 cookies=cookies)
        if response.status_code != 200:
            # Error
            logger.error("Return error with response: {}".format(response.content))
            response.close()
            export_data_restore.status = "Stopped"
            export_data_restore.save()
            return "Cannot connect to destination storage"
    except Exception as e:
        print("Error: ", e)
        response.close()
        export_data_restore.status = "Stopped"
        export_data_restore.save()
        return "Cannot connect to destination storage"

    response_body = response.json()
    data = response_body.data
    response.close()
    if len(data) != 0:
        # Destination storage is not empty, show confirm dialog
        return 'Open Confirm Dialog'

    # Destination storage is empty, start restore process
    return restore_export_data(cookies, export_id, destination_id)


@celery_app.task(bind=True, base=AbortableTask)
def restore_export_data(self, cookies, export_id, destination_id):
    # Check destination storage type (bulk-mounted or add-on)
    destination_region = Region.objects.filter(id=destination_id)
    destination_settings = destination_region.values_list("waterbutler_settings", flat=True)[0]
    destination_folder = destination_settings["storage"]["folder"]
    is_addon_storage = False
    try:
        folder_json = json.loads(destination_folder)
        if not folder_json["encrypt_uploads"]:
            is_addon_storage = True
    except ValueError as e:
        is_addon_storage = True

    if is_addon_storage:
        # If destination storage is add-on institutional storage,
        # move all old data in restore destination storage to a folder to back up (such as '_backup' folder)
        pass

    with transaction.atomic():
        export_data_restore = ExportDataRestore.objects.get(export_id=export_id, destination_id=destination_id)
        # Get file which have same information between export data and database
        # File info file: /export_{process_start}/file_info_{institution_guid}_{process_start}.json
        export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
        export_base_url, export_settings, export_institution_guid = ExportDataLocation.objects.filter(id=export_data.location_id).values_list('waterbutler_url', 'waterbutler_settings', 'institution_guid')[0]
        export_provider = export_settings["storage"]["provider"]
        file_info_path = EXPORT_FILE_INFO_PATH.format(
            institution_guid=export_institution_guid,
            process_start=export_data.process_start.strftime(DATETIME_FORMAT))
        internal = export_base_url == WATERBUTLER_URL
        file_info_url = waterbutler_api_url_for(export_institution_guid, export_provider, path=file_info_path,
                                                _internal=internal, base_url=export_base_url)
        try:
            response = requests.get(file_info_url,
                                    headers={'content-type': 'application/json'},
                                    cookies=cookies)
            if response.status_code != 200:
                # Error
                logger.error("Return error with response: {}".format(response.content))
                response.close()
                export_data_restore.status = "Stopped"
                export_data_restore.save()
                return "Cannot get file infomation list"
        except Exception as e:
            print("Error: ", e)
            response.close()
            export_data_restore.status = "Stopped"
            export_data_restore.save()
            return "Cannot get file infomation list"

        response_body = response.json()
        response.close()
        source_institution = response_body["institution"]
        source_id = source_institution["id"]
        files = response_body["files"]
        for file in files:
            file_path = file["path"]
            file_materialized_path = file["materialized_path"]

            # Add matched file information to related tables

            # Download file from source storage
            download_api = waterbutler_api_url_for(source_id, "S3", path=file_path)
            response = requests.get(download_api)
            response.close()

            # Prepare file name and file path for uploading
            # If the destination storage is add-on institutional storage and source storage is bulk-mounted storage:
            # - for past version files, rename and save each version as filename_{version} in '_version_files' folder
            # - the latest version is saved as the original filename

            # Upload downloaded file to destination storage
            upload_api = waterbutler_api_url_for(destination_id, "S3", path=file_path)
            response = requests.put(upload_api)
            response.close()

        # Update process data with process_end timestamp and "Completed" status
        export_data_restore.process_end = timezone.now()
        export_data_restore.status = "Completed"
        export_data_restore.save()

    return 'Completed'


def rollback_restore(cookies, export_id, destination_id, transaction=None):
    # Rollback transaction
    if transaction is not None:
        transaction.set_rollback(True)

    export_data_restore = ExportDataRestore.objects.get(export_id=export_id, destination_id=destination_id)

    # Rollback file movements
    # Get export data with the file information from the source storage via API call
    export_data = ExportData.objects.filter(id=export_id, is_deleted=False)[0]
    export_base_url, export_settings, export_institution_guid = ExportDataLocation.objects.filter(id=export_data.location_id).values_list('waterbutler_url', 'waterbutler_settings', 'institution_guid')[0]
    export_provider = export_settings["storage"]["provider"]
    file_info_path = EXPORT_FILE_INFO_PATH.format(
        institution_guid=export_institution_guid,
        process_start=export_data.modified.strftime(DATETIME_FORMAT))
    internal = export_base_url == WATERBUTLER_URL
    file_info_url = waterbutler_api_url_for(export_institution_guid, export_provider, path=file_info_path,
                                            _internal=internal, base_url=export_base_url)
    try:
        response = requests.get(file_info_url,
                                headers={'content-type': 'application/json'},
                                cookies=cookies)
        if response.status_code != 200:
            # Error
            logger.error("Return error with response: {}".format(response.content))
            response.close()
            export_data_restore.status = "Stopped"
            export_data_restore.save()
            return "Cannot get file infomation list"
    except Exception as e:
        print("Error: ", e)
        response.close()
        export_data_restore.status = "Stopped"
        export_data_restore.save()
        return "Cannot get file infomation list"

    response_body = response.json()
    response.close()
    source_institution = response_body["institution"]
    source_id = source_institution["id"]
    files = response_body["files"]
    for file in files:
        file_path = file["path"]
        file_materialized_path = file["materialized_path"]
        # In add-on institutional storage: Delete files, except the backup folder.
        # In bulk-mounted institutional storage: Delete only files created during the restore process.
        delete_api = waterbutler_api_url_for(destination_id, "S3", path=file_path)
        response = requests.delete(delete_api)
        response.close()

    # If destination storage is add-on institutional storage
    # Move all files from the backup folder out
    # Delete the backup folder

    export_data_restore.status = "Stopped"
    export_data_restore.save()
    return 'Stopped'
