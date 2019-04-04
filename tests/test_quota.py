# -*- coding: utf-8 -*-
import datetime
import mock
from nose.tools import *  # noqa (PEP8 asserts)
import pytest

from addons.osfstorage.models import OsfStorageFileNode
from api.base import settings as api_settings
from tests.base import OsfTestCase
from osf.models import FileLog, FileInfo, TrashedFileNode, TrashedFolder, UserQuota
from osf_tests.factories import AuthUserFactory, ProjectFactory, UserFactory
from website.util import web_url_for, quota


@pytest.mark.enable_implicit_clean
@pytest.mark.enable_quickfiles_creation
class TestQuotaProfileView(OsfTestCase):
    def setUp(self):
        super(TestQuotaProfileView, self).setUp()
        self.user = AuthUserFactory()
        self.quota_text = '{}%, {}[{}] / {}[GB]'

    def tearDown(self):
        super(TestQuotaProfileView, self).tearDown()

    @mock.patch('website.util.quota.used_quota')
    def test_default_quota(self, mock_usedquota):
        mock_usedquota.return_value = 0

        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        expected = self.quota_text.format(0.0, 0, 'B', api_settings.DEFAULT_MAX_QUOTA)
        assert_in(expected, response.body)

    @mock.patch('website.util.quota.used_quota')
    def test_custom_quota(self, mock_usedquota):
        mock_usedquota.return_value = 0

        UserQuota.objects.create(user=self.user, max_quota=200)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(0.0, 0, 'B', 200), response.body)

    @mock.patch('website.util.quota.used_quota')
    def test_used_quota_bytes(self, mock_usedquota):
        mock_usedquota.return_value = 560

        UserQuota.objects.create(user=self.user, max_quota=100)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(0.0, 560, 'B', 100), response.body)

    @mock.patch('website.util.quota.used_quota')
    def test_used_quota_giga(self, mock_usedquota):
        mock_usedquota.return_value = 5.2 * 1024 ** 3

        UserQuota.objects.create(user=self.user, max_quota=100)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in(self.quota_text.format(5.2, 5.2, 'GB', 100), response.body)

    @mock.patch('website.util.quota.used_quota')
    def test_used_quota_storage_icon_ok(self, mock_usedquota):
        mock_usedquota.return_value = 0

        UserQuota.objects.create(user=self.user, max_quota=100)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in('storage_ok.png', response.body)

    @mock.patch('website.util.quota.used_quota')
    def test_used_quota_storage_icon_warning(self, mock_usedquota):
        mock_usedquota.return_value = 95 * 1024 ** 3

        UserQuota.objects.create(user=self.user, max_quota=100)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in('storage_warning.png', response.body)

    @mock.patch('website.util.quota.used_quota')
    def test_used_quota_storage_icon_error(self, mock_usedquota):
        mock_usedquota.return_value = 105 * 1024 ** 3

        UserQuota.objects.create(user=self.user, max_quota=100)
        response = self.app.get(
            web_url_for('profile_view_id', uid=self.user._id),
            auth=self.user.auth
        )
        assert_in('storage_error.png', response.body)


class TestAbbreviateSize(OsfTestCase):
    def setUp(self):
        super(TestAbbreviateSize, self).setUp()

    def tearDown(self):
        super(TestAbbreviateSize, self).tearDown()

    def test_abbreviate_byte(self):
        abbr_size = quota.abbreviate_size(512)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'B')

    def test_abbreviate_kilobyte(self):
        abbr_size = quota.abbreviate_size(512 * 1024)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'KB')

    def test_abbreviate_megabyte(self):
        abbr_size = quota.abbreviate_size(512 * 1024 ** 2)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'MB')

    def test_abbreviate_gigabyte(self):
        abbr_size = quota.abbreviate_size(512 * 1024 ** 3)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'GB')

    def test_abbreviate_terabyte(self):
        abbr_size = quota.abbreviate_size(512 * 1024 ** 4)
        assert_equal(abbr_size[0], 512)
        assert_equal(abbr_size[1], 'TB')


class TestUsedQuota(OsfTestCase):
    def setUp(self):
        super(TestUsedQuota, self).setUp()
        self.user = UserFactory()
        self.node = [
            ProjectFactory(creator=self.user),
            ProjectFactory(creator=self.user)
        ]

    def tearDown(self):
        super(TestUsedQuota, self).tearDown()

    def test_calculate_used_quota(self):
        file_list = []

        # No files
        assert_equal(quota.used_quota(self.user._id), 0)

        # Add a file to node[0]
        file_list.append(OsfStorageFileNode.create(
            target=self.node[0],
            name='file0'
        ))
        file_list[0].save()
        FileInfo.objects.create(file=file_list[0], file_size=500)
        assert_equal(quota.used_quota(self.user._id), 500)

        # Add a file to node[1]
        file_list.append(OsfStorageFileNode.create(
            target=self.node[1],
            name='file1'
        ))
        file_list[1].save()
        FileInfo.objects.create(file=file_list[1], file_size=1000)
        assert_equal(quota.used_quota(self.user._id), 1500)

    def test_calculate_used_quota_deleted_file(self):
        # Add a (deleted) file to node[0]
        file_node = OsfStorageFileNode.create(
            target=self.node[0],
            name='file0',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file_node.save()
        FileInfo.objects.create(file=file_node, file_size=500)
        assert_equal(quota.used_quota(self.user._id), 0)


class TestSaveUsedQuota(OsfTestCase):
    def setUp(self):
        super(TestSaveUsedQuota, self).setUp()
        self.user = UserFactory()
        self.project_creator = UserFactory()
        self.node = ProjectFactory(creator=self.project_creator)
        self.file = OsfStorageFileNode.create(
            target=self.node,
            path='/testfile',
            _id='testfile',
            name='testfile',
            materialized_path='/testfile'
        )
        self.file.save()

    def test_add_first_file(self):
        assert_false(UserQuota.objects.filter(user=self.project_creator).exists())

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserQuota.objects.filter(user=self.project_creator).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 1000)

    def test_add_file(self):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': 1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )

        user_quota = UserQuota.objects.filter(user=self.project_creator).all()
        assert_equal(len(user_quota), 1)
        user_quota = user_quota[0]
        assert_equal(user_quota.used, 6500)

    def test_add_file_negative_size(self):
        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_ADDED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': '/' + self.file._id,
                    'kind': 'file',
                    'size': -1000,
                    'created_utc': '',
                    'modified_utc': '',
                    'extra': {'version': '1'}
                }
            }
        )
        assert_false(UserQuota.objects.filter(user=self.project_creator).exists())

    def test_delete_file(self):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserQuota.objects.get(user=self.project_creator)
        assert_equal(user_quota.used, 4500)

    def test_delete_file_lower_used_quota(self):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserQuota.objects.get(user=self.project_creator)
        assert_equal(user_quota.used, 0)

    @mock.patch('website.util.quota.logging')
    def test_delete_file_invalid_file(self, mock_logging):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': 'malicioususereditedthis',
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserQuota.objects.get(user=self.project_creator)
        assert_equal(user_quota.used, 5500)
        mock_logging.error.assert_called_with('FileNode not found, cannot update used quota!')

    @mock.patch('website.util.quota.logging')
    def test_delete_file_without_fileinfo(self, mock_logging):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserQuota.objects.get(user=self.project_creator)
        assert_equal(user_quota.used, 5500)
        mock_logging.error.assert_called_with('FileInfo not found, cannot update used quota!')

    @mock.patch('website.util.quota.logging')
    def test_delete_file_not_trashed(self, mock_logging):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        user_quota = UserQuota.objects.get(user=self.project_creator)
        assert_equal(user_quota.used, 5500)
        mock_logging.error.assert_called_with('FileNode is not trashed, cannot update used quota!')

    def test_delete_file_without_userquota(self):
        FileInfo.objects.create(file=self.file, file_size=1000)

        self.file.deleted_on = datetime.datetime.now()
        self.file.deleted_by = self.user
        self.file.type = 'osf.trashedfile'
        self.file.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfile',
                    'materialized': '/filename',
                    'path': self.file._id,
                    'kind': 'file',
                    'extra': {}
                }
            }
        )

        assert_false(UserQuota.objects.filter(user=self.project_creator).exists())

    def test_delete_folder(self):
        UserQuota.objects.create(
            user=self.project_creator,
            storage_type=UserQuota.NII_STORAGE,
            max_quota=api_settings.DEFAULT_MAX_QUOTA,
            used=5500
        )

        folder = TrashedFolder(
            target=self.node,
            name='testfolder',
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        folder.save()
        file1 = TrashedFileNode.create(
            target=self.node,
            name='testfile1',
            parent_id=folder.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file1.provider = 'osfstorage'
        file1.save()
        file2 = TrashedFileNode.create(
            target=self.node,
            name='testfile2',
            parent_id=folder.id,
            deleted_on=datetime.datetime.now(),
            deleted_by=self.user
        )
        file2.provider = 'osfstorage'
        file2.save()

        file1_info = FileInfo(file=file1, file_size=2000)
        file1_info.save()
        file2_info = FileInfo(file=file2, file_size=3000)
        file2_info.save()

        quota.update_used_quota(
            self=None,
            target=self.node,
            user=self.user,
            event_type=FileLog.FILE_REMOVED,
            payload={
                'provider': 'osfstorage',
                'metadata': {
                    'provider': 'osfstorage',
                    'name': 'testfolder',
                    'materialized': '/testfolder',
                    'path': '{}/'.format(folder._id),
                    'kind': 'folder',
                    'extra': {}
                }
            }
        )

        user_quota = UserQuota.objects.get(user=self.project_creator)
        assert_equal(user_quota.used, 500)
