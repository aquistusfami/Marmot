import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from marmot.analyzer import DiskAnalyzer


class TestDiskAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = DiskAnalyzer()

    @patch('pathlib.Path.exists', return_value=True)
    @patch('pathlib.Path.is_dir', return_value=True)
    def test_set_path_valid(self, mock_is_dir, mock_exists):
        self.analyzer.set_path('/tmp')
        self.assertEqual(self.analyzer.current_path, Path('/tmp'))

    @patch('pathlib.Path.exists', return_value=False)
    def test_set_path_invalid(self, mock_exists):
        old_path = self.analyzer.current_path
        self.analyzer.set_path('/invalid/path')
        self.assertEqual(self.analyzer.current_path, old_path)

    def test_recursive_size(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            Path(d, "sub").mkdir()
            Path(d, "a.bin").write_bytes(b"x" * 600)
            Path(d, "sub", "b.bin").write_bytes(b"x" * 400)
            Path(d, "link").symlink_to(Path(d, "a.bin"))  # symlinks are not counted twice
            self.assertEqual(self.analyzer._recursive_size(d), 1000)
            # cached: deleting a file does not change the answer until invalidate()
            Path(d, "a.bin").unlink()
            self.assertEqual(self.analyzer._recursive_size(d), 1000)
            self.analyzer.invalidate()
            self.assertEqual(self.analyzer._recursive_size(d), 400)

    def test_scan_cancel(self):
        import tempfile

        from marmot.analyzer import ScanCancelled
        with tempfile.TemporaryDirectory() as d:
            Path(d, "sub").mkdir()
            self.analyzer.set_path(d)
            with self.assertRaises(ScanCancelled):
                self.analyzer.scan_current(cancelled=lambda: True)

    @patch('os.scandir')
    @patch('marmot.analyzer.DiskAnalyzer._recursive_size', return_value=1200)
    def test_scan_current(self, mock_rec_size, mock_scandir):
        # Mock directory entry
        entry_dir = MagicMock()
        entry_dir.name = 'projects'
        entry_dir.path = '/home/user/projects'
        entry_dir.is_dir.return_value = True
        
        # Mock file entry
        entry_file = MagicMock()
        entry_file.name = 'notes.txt'
        entry_file.path = '/home/user/notes.txt'
        entry_file.is_dir.return_value = False
        entry_file.stat.return_value.st_size = 300
        
        mock_scandir.return_value = [entry_dir, entry_file]
        
        items = self.analyzer.scan_current()
        
        self.assertEqual(len(items), 2)
        # Sorted by size descending, so 'projects' (1200) comes first
        self.assertEqual(items[0]['name'], 'projects')
        self.assertEqual(items[0]['size'], 1200)
        self.assertTrue(items[0]['is_dir'])
        
        self.assertEqual(items[1]['name'], 'notes.txt')
        self.assertEqual(items[1]['size'], 300)
        self.assertFalse(items[1]['is_dir'])

    def test_format_size_zero(self):
        self.assertEqual(self.analyzer.format_size(0), "0 B")

    @patch('os.lstat')
    def test_recursive_size_file(self, mock_lstat):
        import stat
        file_stat = MagicMock()
        file_stat.st_mode = stat.S_IFREG
        file_stat.st_size = 750
        mock_lstat.return_value = file_stat
        
        size = self.analyzer._recursive_size('/tmp/somefile')
        self.assertEqual(size, 750)

    @patch('os.lstat')
    def test_recursive_size_symlink(self, mock_lstat):
        import stat
        link_stat = MagicMock()
        link_stat.st_mode = stat.S_IFLNK
        link_stat.st_size = 12
        mock_lstat.return_value = link_stat
        
        size = self.analyzer._recursive_size('/tmp/somelink')
        self.assertEqual(size, 0)

    @patch('os.lstat', side_effect=OSError("Access denied"))
    def test_recursive_size_oserror(self, mock_lstat):
        size = self.analyzer._recursive_size('/tmp/protected')
        self.assertEqual(size, 0)

    @patch('os.scandir')
    def test_scan_current_oserror(self, mock_scandir):
        # entry throws OSError during iteration/stat
        entry = MagicMock()
        entry.is_dir.side_effect = OSError("Read error")
        mock_scandir.return_value = [entry]
        
        items = self.analyzer.scan_current()
        self.assertEqual(len(items), 0)

    @patch('os.scandir', side_effect=Exception("Disk error"))
    def test_scan_current_exception(self, mock_scandir):
        items = self.analyzer.scan_current()
        self.assertEqual(len(items), 0)
