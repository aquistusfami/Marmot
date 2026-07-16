import os
import tempfile
import unittest
from unittest.mock import patch, mock_open, MagicMock
from modules.monitor import SystemMonitor

class TestSystemMonitor(unittest.TestCase):
    @patch('modules.monitor.SystemMonitor.get_cpu_usage', return_value=0.0)
    @patch('modules.monitor.SystemMonitor.get_network_io', return_value={})
    def setUp(self, mock_net, mock_cpu):
        self.monitor = SystemMonitor()

    @patch('builtins.open', new_callable=mock_open, read_data="cpu  100 200 300 400 500 600 700 800\n")
    def test_get_cpu_usage_success(self, mock_file):
        # Reset last values to trigger non-zero delta
        self.monitor.last_cpu_idle = 0.0
        self.monitor.last_cpu_total = 0.0
        
        usage = self.monitor.get_cpu_usage()
        # Sum of fields: 100+200+300+400+500+600+700+800 = 3600
        # Idle = fields[3] + fields[4] = 400 + 500 = 900
        # usage = (1 - (900/3600)) * 100 = 75.0%
        self.assertEqual(usage, 75.0)

    @patch('builtins.open', side_effect=Exception("Read error"))
    def test_get_cpu_usage_exception(self, mock_file):
        usage = self.monitor.get_cpu_usage()
        self.assertEqual(usage, 0.0)

    @patch('builtins.open', new_callable=mock_open, read_data="MemTotal:        16000000 kB\nMemFree:          4000000 kB\nMemAvailable:     8000000 kB\nSwapTotal:        2000000 kB\nSwapFree:         1500000 kB\n")
    def test_get_memory_info_success(self, mock_file):
        mem = self.monitor.get_memory_info()
        self.assertEqual(mem['total'], 16000000 * 1024)
        self.assertEqual(mem['available'], 8000000 * 1024)
        self.assertEqual(mem['used'], (16000000 - 8000000) * 1024)
        self.assertEqual(mem['percent'], 50.0)
        self.assertEqual(mem['swap_total'], 2000000 * 1024)
        self.assertEqual(mem['swap_used'], 512000000) # (2000000-1500000)*1024 = 512MB
        self.assertEqual(mem['swap_percent'], 25.0)

    @patch('builtins.open', side_effect=Exception)
    def test_get_memory_info_exception(self, mock_file):
        mem = self.monitor.get_memory_info()
        self.assertEqual(mem['total'], 0)
        self.assertEqual(mem['percent'], 0.0)

    @patch('builtins.open', new_callable=mock_open, read_data="Inter-|   Receive\n face |bytes\n  eth0:    1000 1 2 3 4 5 6 7     2000 1 2 3 4 5 6 7\n")
    def test_get_network_io(self, mock_file):
        # First call to populate last bytes
        self.monitor.last_net_bytes = {}
        with patch('time.time', return_value=100.0):
            self.monitor.get_network_io()
            
        # Second call to calculate speed
        with patch('time.time', return_value=102.0):
            # Update read data for higher bytes
            mock_file.return_value.readlines.return_value = [
                "Inter-|   Receive\n",
                " face |bytes\n",
                "  eth0:    3000 1 2 3 4 5 6 7     6000 1 2 3 4 5 6 7\n"
            ]
            stats = self.monitor.get_network_io()
            
        self.assertIn('eth0', stats)
        # rx_speed = (3000 - 1000) / 2.0 = 1000.0 B/s
        # tx_speed = (6000 - 2000) / 2.0 = 2000.0 B/s
        self.assertEqual(stats['eth0']['rx_speed'], 1000.0)
        self.assertEqual(stats['eth0']['tx_speed'], 2000.0)

    @patch('os.path.exists', return_value=True)
    @patch('os.listdir', return_value=['thermal_zone0'])
    def test_get_temperature_thermal_zone(self, mock_listdir, mock_exists):
        def mock_open_temp(path, mode='r'):
            if 'type' in str(path):
                return mock_open(read_data="x86_pkg_temp\n")()
            elif 'temp' in str(path):
                return mock_open(read_data="45000\n")()
            raise FileNotFoundError()
            
        with patch('builtins.open', side_effect=mock_open_temp):
            temp = self.monitor.get_temperature()
            self.assertEqual(temp, 45.0)

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_get_battery_info(self, mock_listdir, mock_exists):
        # Simulate BAT0 supply exists
        mock_exists.side_effect = lambda path: 'power_supply' in str(path) or 'BAT0' in str(path) or 'capacity' in str(path) or 'status' in str(path) or 'power_now' in str(path)
        mock_listdir.return_value = ['BAT0']
        
        def mock_open_bat(path, mode='r'):
            if 'capacity' in str(path):
                return mock_open(read_data="85\n")()
            elif 'status' in str(path):
                return mock_open(read_data="Discharging\n")()
            elif 'power_now' in str(path):
                return mock_open(read_data="15000000\n")()
            raise FileNotFoundError()
            
        with patch('builtins.open', side_effect=mock_open_bat):
            bat = self.monitor.get_battery_info()
            self.assertTrue(bat['present'])
            self.assertEqual(bat['capacity'], 85)
            self.assertEqual(bat['status'], "Discharging")
            self.assertEqual(bat['power'], 15.0)

    @patch('builtins.open', new_callable=mock_open, read_data="/dev/sda1 / ext4 rw 0 0\n")
    @patch('os.statvfs')
    def test_get_disk_usage(self, mock_statvfs, mock_file):
        mock_stat = MagicMock()
        mock_stat.f_blocks = 1000
        mock_stat.f_frsize = 4096
        mock_stat.f_bfree = 400
        mock_stat.f_bavail = 350
        mock_statvfs.return_value = mock_stat
        
        usage = self.monitor.get_disk_usage()
        self.assertEqual(len(usage), 1)
        self.assertEqual(usage[0]['device'], '/dev/sda1')
        self.assertEqual(usage[0]['mountpoint'], '/')
        self.assertEqual(usage[0]['total'], 4096000)
        self.assertEqual(usage[0]['used'], 2457600)
        self.assertEqual(usage[0]['available'], 1433600)
        self.assertEqual(usage[0]['percent'], 60.0)

    @patch('builtins.open', new_callable=mock_open, read_data="cpu  100 200 300 400 500 600 700 800\n")
    def test_get_cpu_usage_delta_zero(self, mock_file):
        # Set last values equal to what we read to force delta_total = 0
        self.monitor.last_cpu_idle = 900.0
        self.monitor.last_cpu_total = 3600.0
        
        usage = self.monitor.get_cpu_usage()
        self.assertEqual(usage, 0.0)

    @patch('builtins.open', new_callable=mock_open, read_data="Inter-|   Receive\n face |bytes\n  lo:    100 1 2 3 4 5 6 7     100 1 2 3 4 5 6 7\n  eth0:    100 1 2 3 4 5 6 7     200 1 2 3 4 5 6 7\n  invalidline\n")
    def test_get_network_io_skip_lines(self, mock_file):
        self.monitor.last_net_bytes = {}
        stats = self.monitor.get_network_io()
        # Should skip 'lo' and 'invalidline', only having 'eth0'
        self.assertIn('eth0', stats)
        self.assertNotIn('lo', stats)

    @patch('builtins.open', side_effect=Exception("Dev read error"))
    def test_get_network_io_exception(self, mock_file):
        stats = self.monitor.get_network_io()
        self.assertEqual(stats, {})

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_get_temperature_hwmon(self, mock_listdir, mock_exists):
        # Simulate thermal classes don't exist but hwmon exists
        mock_exists.side_effect = lambda path: 'hwmon' in str(path) or 'name' in str(path) or 'temp1_input' in str(path)
        
        def custom_listdir(path):
            if str(path) == '/sys/class/hwmon':
                return ['hwmon0']
            elif str(path) == '/sys/class/hwmon/hwmon0':
                return ['name', 'temp1_input']
            return []
        mock_listdir.side_effect = custom_listdir
        
        def mock_open_hwmon(path, mode='r'):
            if 'name' in str(path):
                return mock_open(read_data="coretemp\n")()
            elif 'temp1_input' in str(path):
                return mock_open(read_data="38000\n")()
            raise FileNotFoundError()
            
        with patch('builtins.open', side_effect=mock_open_hwmon):
            temp = self.monitor.get_temperature()
            self.assertEqual(temp, 38.0)

    @patch('os.path.exists')
    @patch('os.listdir')
    def test_get_battery_info_current_voltage_fallback(self, mock_listdir, mock_exists):
        # BAT0 exists with current_now and voltage_now instead of power_now
        mock_exists.side_effect = lambda path: str(path).endswith('power_supply') or \
                                               str(path).endswith('BAT0') or \
                                               str(path).endswith('capacity') or \
                                               str(path).endswith('status') or \
                                               str(path).endswith('current_now') or \
                                               str(path).endswith('voltage_now')
        mock_listdir.return_value = ['BAT0']
        
        def mock_open_bat(path, mode='r'):
            if 'capacity' in str(path):
                return mock_open(read_data="90\n")()
            elif 'status' in str(path):
                return mock_open(read_data="Charging\n")()
            elif 'current_now' in str(path):
                return mock_open(read_data="2000000\n")() # 2A
            elif 'voltage_now' in str(path):
                return mock_open(read_data="12000000\n")() # 12V
            raise FileNotFoundError()
            
        with patch('builtins.open', side_effect=mock_open_bat):
            bat = self.monitor.get_battery_info()
            self.assertTrue(bat['present'])
            self.assertEqual(bat['capacity'], 90)
            self.assertEqual(bat['status'], "Charging")
            # power = 2000000 * 12000000 / 1e12 = 24.0W
            self.assertEqual(bat['power'], 24.0)

    @patch('os.path.exists', side_effect=Exception("Power Supply read error"))
    def test_get_battery_info_exception(self, mock_exists):
        bat = self.monitor.get_battery_info()
        self.assertFalse(bat['present'])

    @patch('builtins.open', side_effect=Exception("Mounts read error"))
    def test_get_disk_usage_exception(self, mock_file):
        usage = self.monitor.get_disk_usage()
        self.assertEqual(usage, [])
