import os
import shutil
import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path
from modules.cleaner import SystemCleaner

class TestSystemCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = SystemCleaner()

    def test_format_size(self):
        self.assertEqual(self.cleaner.format_size(0), "0 B")
        self.assertEqual(self.cleaner.format_size(512), "512.00 B")
        self.assertEqual(self.cleaner.format_size(1024 * 1.5), "1.50 KB")
        self.assertEqual(self.cleaner.format_size(1024 * 1024 * 2.3), "2.30 MB")
        self.assertEqual(self.cleaner.format_size(1024 * 1024 * 1024 * 4.5), "4.50 GB")

    @patch('os.walk')
    @patch('os.path.getsize')
    @patch('os.path.islink', return_value=False)
    def test_get_dir_size_directory(self, mock_islink, mock_getsize, mock_walk):
        mock_walk.return_value = [
            ('/tmp/test', ('subdir',), ('file1.txt', 'file2.txt')),
        ]
        mock_getsize.side_effect = [100, 200]
        
        size = self.cleaner.get_dir_size(Path('/tmp/test'))
        self.assertEqual(size, 300)

    @patch('shutil.rmtree')
    @patch('os.makedirs')
    def test_clean_user_cache(self, mock_makedirs, mock_rmtree):
        scan_details = {
            'user_cache': {
                'path': '/home/user/.cache'
            }
        }
        with patch('pathlib.Path.exists', return_value=True):
            success, msg = self.cleaner.clean('user_cache', scan_details)
            self.assertTrue(success)
            self.assertEqual(msg, "User caches cleaned successfully")
            mock_rmtree.assert_called_once_with(Path('/home/user/.cache'), ignore_errors=True)

    @patch('shutil.rmtree')
    @patch('os.makedirs')
    def test_clean_trash(self, mock_makedirs, mock_rmtree):
        scan_details = {
            'trash': {
                'path': '/home/user/.local/share/Trash'
            }
        }
        with patch('pathlib.Path.exists', return_value=True):
            success, msg = self.cleaner.clean('trash', scan_details)
            self.assertTrue(success)
            self.assertEqual(msg, "Trash bin emptied successfully")

    @patch('subprocess.run')
    def test_clean_apt_cache_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        scan_details = {'apt_cache': {'path': '/var/cache/apt/archives'}}
        success, msg = self.cleaner.clean('apt_cache', scan_details)
        self.assertTrue(success)
        self.assertIn("Apt packages cache cleaned successfully", msg)

    @patch('subprocess.run')
    def test_clean_systemd_logs_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = b"Vacuuming done\n"
        mock_run.return_value = mock_res
        
        scan_details = {'systemd_logs': {'path': '/var/log/journal'}}
        success, msg = self.cleaner.clean('systemd_logs', scan_details)
        self.assertTrue(success)
        self.assertIn("Systemd logs vacuumed", msg)

    @patch('shutil.rmtree')
    def test_clean_dev_junk(self, mock_rmtree):
        scan_details = {
            'dev_junk': {
                'paths_list': ['/home/user/Projects/test/node_modules', '/home/user/Projects/test/.venv']
            }
        }
        success, msg = self.cleaner.clean('dev_junk', scan_details)
        self.assertTrue(success)
        self.assertEqual(msg, "Cleaned 2 build folder(s)")
        self.assertEqual(mock_rmtree.call_count, 2)

    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.is_dir', return_value=True)
    @patch('subprocess.check_output', return_value=b"Archived and active journals take up 120.4MB in the file system.\n")
    @patch('modules.cleaner.SystemCleaner.get_dir_size', return_value=5000000)
    def test_scan_success(self, mock_get_size, mock_check_output, mock_is_dir, mock_exists):
        # We also mock iterdir to return some folders representing dev junk
        mock_proj = MagicMock()
        mock_proj.is_dir.return_value = True
        mock_proj.name = "my_project"
        mock_proj.__str__.return_value = "/home/user/Projects/my_project"
        
        # Iterdir inside search_dirs
        with patch('pathlib.Path.iterdir', return_value=[mock_proj]):
            results = self.cleaner.scan()
            
        self.assertIn('user_cache', results)
        self.assertEqual(results['user_cache']['size'], 5000000)
        self.assertIn('trash', results)
        self.assertIn('apt_cache', results)
        self.assertIn('systemd_logs', results)
        self.assertEqual(results['systemd_logs']['size_str'], "120.4MB")
        self.assertIn('dev_junk', results)

    def test_clean_item_not_found(self):
        success, msg = self.cleaner.clean('user_cache', {})
        self.assertFalse(success)
        self.assertEqual(msg, "Item not found in scan details")

    @patch('pathlib.Path.exists', return_value=False)
    def test_clean_user_cache_not_exists(self, mock_exists):
        scan_details = {'user_cache': {'path': '/non_existent_cache'}}
        success, msg = self.cleaner.clean('user_cache', scan_details)
        self.assertFalse(success)
        self.assertEqual(msg, "Cache directory does not exist")

    @patch('pathlib.Path.exists', return_value=False)
    def test_clean_trash_not_exists(self, mock_exists):
        scan_details = {'trash': {'path': '/non_existent_trash'}}
        success, msg = self.cleaner.clean('trash', scan_details)
        self.assertFalse(success)
        self.assertEqual(msg, "Trash directory does not exist")

    @patch('subprocess.run', side_effect=Exception("Execution failed"))
    def test_clean_apt_cache_all_fail(self, mock_run):
        scan_details = {'apt_cache': {'path': '/var/cache/apt/archives'}}
        success, msg = self.cleaner.clean('apt_cache', scan_details)
        self.assertFalse(success)
        self.assertIn("Failed to execute", msg)

    @patch('subprocess.run', side_effect=Exception("Execution failed"))
    def test_clean_systemd_logs_all_fail(self, mock_run):
        scan_details = {'systemd_logs': {'path': '/var/log/journal'}}
        success, msg = self.cleaner.clean('systemd_logs', scan_details)
        self.assertFalse(success)
        self.assertIn("Failed to execute", msg)

    def test_clean_unknown_item(self):
        scan_details = {'unknown': {'path': '/some/path'}}
        success, msg = self.cleaner.clean('unknown', scan_details)
        self.assertFalse(success)
        self.assertEqual(msg, "Unknown item")
