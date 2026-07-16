import unittest
from unittest.mock import patch, MagicMock, mock_open
from modules.optimizer import SystemOptimizer

class TestSystemOptimizer(unittest.TestCase):
    def setUp(self):
        self.optimizer = SystemOptimizer()

    def test_get_optimizations(self):
        opts = self.optimizer.get_optimizations()
        self.assertEqual(len(opts), 4)
        ids = [o['id'] for o in opts]
        self.assertIn('drop_caches', ids)
        self.assertIn('flush_dns', ids)
        self.assertIn('reset_services', ids)
        self.assertIn('swap_reset', ids)

    @patch('subprocess.run')
    def test_run_optimization_drop_caches_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        success, msg = self.optimizer.run_optimization("drop_caches")
        self.assertTrue(success)
        self.assertEqual(msg, "RAM page cache dropped successfully")
        self.assertEqual(mock_run.call_count, 2) # sync and pkexec drop_caches

    @patch('subprocess.run')
    def test_run_optimization_reset_services_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        success, msg = self.optimizer.run_optimization("reset_services")
        self.assertTrue(success)
        self.assertEqual(msg, "Failed Systemd services status reset successfully")

    @patch('subprocess.run')
    def test_run_optimization_flush_dns_resolved(self, mock_run):
        # First call is systemctl is-active -> success
        # Second call is resolvectl flush-caches -> success
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        success, msg = self.optimizer.run_optimization("flush_dns")
        self.assertTrue(success)
        self.assertEqual(msg, "DNS cache flushed via resolvectl")

    @patch('subprocess.run')
    def test_run_optimization_flush_dns_nscd(self, mock_run):
        # First call is systemctl is-active -> fails (resolved inactive)
        # Second call is pkexec systemctl restart nscd -> success
        import subprocess
        mock_res_ok = MagicMock()
        mock_res_ok.returncode = 0
        
        mock_run.side_effect = [subprocess.CalledProcessError(1, cmd="is-active"), mock_res_ok]
        
        success, msg = self.optimizer.run_optimization("flush_dns")
        self.assertTrue(success)
        self.assertEqual(msg, "DNS cache flushed by restarting nscd service")

    @patch('builtins.open', new_callable=mock_open, read_data="MemAvailable:     8000000 kB\nSwapTotal:        2000000 kB\nSwapFree:         1900000 kB\n")
    @patch('subprocess.run')
    def test_run_optimization_swap_reset_safe(self, mock_run, mock_file):
        # Available memory = 8GB, swap used = 100MB (safe)
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res
        
        success, msg = self.optimizer.run_optimization("swap_reset")
        self.assertTrue(success)
        self.assertEqual(msg, "Swap space reclaimed and cycled successfully")

    @patch('builtins.open', new_callable=mock_open, read_data="MemAvailable:      100000 kB\nSwapTotal:        2000000 kB\nSwapFree:         1000000 kB\n")
    def test_run_optimization_swap_reset_unsafe(self, mock_file):
        # Available memory = 100MB, swap used = 1GB (unsafe, should block!)
        success, msg = self.optimizer.run_optimization("swap_reset")
        self.assertFalse(success)
        self.assertIn("Safety warning", msg)
