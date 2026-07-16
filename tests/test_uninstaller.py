import os
import shutil
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from modules.uninstaller import PackageUninstaller

class TestPackageUninstaller(unittest.TestCase):
    def setUp(self):
        self.uninstaller = PackageUninstaller()

    @patch('subprocess.Popen')
    def test_list_installed_packages(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"curl\t7.88.1\tcommand line tool\nlibcurl4\t7.88.1\tshared library\n", None)
        mock_popen.return_value = mock_proc
        
        # Test all packages
        pkgs = self.uninstaller.list_installed_packages()
        self.assertEqual(len(pkgs), 2)
        self.assertEqual(pkgs[0]['name'], 'curl')
        self.assertEqual(pkgs[1]['name'], 'libcurl4')
        
        # Test search query
        pkgs_filtered = self.uninstaller.list_installed_packages(search_query="shared")
        self.assertEqual(len(pkgs_filtered), 1)
        self.assertEqual(pkgs_filtered[0]['name'], 'libcurl4')

    @patch('os.walk')
    @patch('os.path.getsize', return_value=100)
    def test_find_remnants(self, mock_getsize, mock_walk):
        orig_exists = Path.exists
        orig_is_dir = Path.is_dir
        
        target_path = str(Path.home() / ".config" / "curl")
        
        def custom_exists(self_path):
            return str(self_path) == target_path or str(self_path) in [
                str(Path.home() / ".config"),
                str(Path.home() / ".local" / "share"),
                str(Path.home() / ".cache"),
                str(Path.home())
            ]
            
        def custom_is_dir(self_path):
            return custom_exists(self_path)
            
        Path.exists = custom_exists
        Path.is_dir = custom_is_dir
        
        try:
            # We need mock_walk to return mock directory structure
            mock_walk.return_value = [
                ('/home/user/.config/curl', (), ('config.json',)),
            ]
            
            # Use a real Path object for mock_entry
            mock_entry = Path(target_path)
            
            with patch('pathlib.Path.iterdir', return_value=[mock_entry]):
                remnants = self.uninstaller.find_remnants("curl")
                
            self.assertEqual(len(remnants), 1)
            self.assertEqual(remnants[0]['path'], str(Path.home() / ".config" / "curl"))
            self.assertEqual(remnants[0]['size'], 100)
        finally:
            Path.exists = orig_exists
            Path.is_dir = orig_is_dir

    @patch('subprocess.run')
    @patch('shutil.rmtree')
    def test_uninstall_success(self, mock_rmtree, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        success, msg = self.uninstaller.uninstall("curl", delete_remnants=["/home/user/.config/curl"])
        self.assertTrue(success)
        self.assertIn("purged successfully", msg)
        self.assertIn("Cleared user config remnants", msg)
        mock_rmtree.assert_called_once_with("/home/user/.config/curl", ignore_errors=True)

    @patch('subprocess.run')
    def test_uninstall_failure(self, mock_run):
        # Both pkexec and sudo fail
        mock_res = MagicMock()
        mock_res.returncode = 1
        mock_res.stderr = b"Permission denied\n"
        mock_run.return_value = mock_res
        
        success, msg = self.uninstaller.uninstall("curl")
        self.assertFalse(success)
        self.assertIn("Failed to purge package", msg)
