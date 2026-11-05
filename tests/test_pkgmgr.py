import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from marmot import pkgmgr
from marmot.cleaner import SystemCleaner
from marmot.uninstaller import PackageUninstaller

PACMAN_QI = """Name            : git
Version         : 2.51.0-1
Description     : the fast distributed version control system
Depends On      : curl  expat
                  perl

Name            : niri
Version         : 25.08-1
Description     : A scrollable-tiling Wayland compositor
"""


class TestParsers(unittest.TestCase):
    def test_pacman_qi(self):
        pkgs = pkgmgr._parse_pacman_qi(PACMAN_QI)
        self.assertEqual([p['name'] for p in pkgs], ["git", "niri"])
        self.assertEqual(pkgs[0]['version'], "2.51.0-1")
        self.assertEqual(pkgs[1]['summary'], "A scrollable-tiling Wayland compositor")

    def test_apt_sim(self):
        out = "Reading package lists...\nPurg curl [7.88]\nPurg libcurl4 [7.88]\nInst foo\n"
        self.assertEqual(pkgmgr._parse_apt_sim(out), ["curl", "libcurl4"])

    def test_pacman_backend_commands(self):
        pm = pkgmgr.get("pacman")
        self.assertEqual(pm['remove_cmd']("git"), ["pacman", "-Rns", "--noconfirm", "git"])
        self.assertIn("-Rsp", pm['preview_cmd']("git"))


class TestPacmanUninstaller(unittest.TestCase):
    @patch('subprocess.Popen')
    def test_list_and_search(self, mock_popen):
        proc = MagicMock()
        proc.communicate.return_value = (PACMAN_QI.encode(), None)
        mock_popen.return_value = proc
        un = PackageUninstaller(backend="pacman")
        self.assertEqual(len(un.list_installed_packages()), 2)
        self.assertEqual([p['name'] for p in un.list_installed_packages("wayland")], ["niri"])

    @patch('subprocess.run')
    def test_preview(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=b"git\nperl-error\n")
        self.assertEqual(PackageUninstaller(backend="pacman").preview_removal("git"), ["git", "perl-error"])
        mock_run.return_value = MagicMock(returncode=1, stdout=b"")
        self.assertIsNone(PackageUninstaller(backend="pacman").preview_removal("glibc"))

    @patch('subprocess.run')
    @patch('shutil.rmtree')
    def test_uninstall_uses_pacman(self, mock_rmtree, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ok, _ = PackageUninstaller(backend="pacman").uninstall("git")
        self.assertTrue(ok)
        self.assertEqual(mock_run.call_args_list[0].args[0], ["pkexec", "pacman", "-Rns", "--noconfirm", "git"])


class TestRemnantSafety(unittest.TestCase):
    def test_exact_match_only_and_refuses_outside_paths(self):
        with tempfile.TemporaryDirectory() as home, patch('pathlib.Path.home', return_value=Path(home)):
            for d in ("git", "gitkraken", "GitHub Desktop"):
                (Path(home) / ".config" / d).mkdir(parents=True)
            un = PackageUninstaller(backend="pacman")
            self.assertEqual([r['path'] for r in un.find_remnants("git")], [str(Path(home) / ".config" / "git")])
            self.assertFalse(un.is_safe_remnant(home))
            self.assertFalse(un.is_safe_remnant(str(Path(home) / "Documents" / "git")))
            self.assertTrue(un.is_safe_remnant(str(Path(home) / ".config" / "git")))


class TestDevJunk(unittest.TestCase):
    def test_markers_required(self):
        with tempfile.TemporaryDirectory() as home, patch('pathlib.Path.home', return_value=Path(home)):
            h = Path(home)
            (h / "web" / "node_modules").mkdir(parents=True)
            (h / "web" / "package.json").touch()
            (h / "photos" / "build").mkdir(parents=True)          # no project file: real user data
            (h / "rs" / "target").mkdir(parents=True)             # no Cargo.toml
            with patch('subprocess.check_output', side_effect=Exception):
                paths = SystemCleaner(backend="pacman").scan()['dev_junk']['paths_list']
            self.assertEqual(paths, [str(h / "web" / "node_modules")])

    def test_skips_marmot_own_venv(self):
        import marmot.cleaner as c
        with tempfile.TemporaryDirectory() as home, patch('pathlib.Path.home', return_value=Path(home)):
            proj = Path(home) / "Marmot"
            (proj / ".venv").mkdir(parents=True)
            (proj / "requirements.txt").touch()
            with patch.object(c, "RUNNING_VENV", (proj / ".venv").resolve()), patch('subprocess.check_output', side_effect=Exception):
                self.assertEqual(SystemCleaner(backend="pacman").scan()['dev_junk']['paths_list'], [])


if __name__ == "__main__":
    unittest.main()
