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


DNF_REMOVE = """Package                     Arch   Version         Repository      Size
Removing:
 python3-requests           noarch 0:2.34.2-2.fc45 fedora     679.2 KiB
Removing unused dependencies:
 python3-idna               noarch 0:3.18-2.fc45   fedora     523.7 KiB
 python3-urllib3+socks      noarch 0:2.8.0-3.fc45  updates      0.0   B

Transaction Summary:
 Removing:          3 packages
"""

ZYPPER_REMOVE = """Reading installed packages...
The following 3 packages are going to be REMOVED:
  libexpat1 python313-requests
  python313-urllib3

3 packages to remove.
"""

ZYPPER_UNNEEDED = """S  | Repository | Name        | Version | Arch
---+------------+-------------+---------+-------
i  | repo-oss   | libfoo1     | 1.0-1.1 | x86_64
i  | repo-oss   | python3-bar | 2.0-2.1 | noarch
"""


class TestMoreBackends(unittest.TestCase):
    def test_dnf_remove_preview(self):
        self.assertEqual(pkgmgr._parse_dnf_remove(DNF_REMOVE),
                         ["python3-requests", "python3-idna", "python3-urllib3+socks"])

    def test_dnf_failed_preview_is_empty(self):
        out = "Failed to resolve the transaction:\nProblem 1: ... protected packages: dnf5\n"
        self.assertEqual(pkgmgr._parse_dnf_remove(out), [])

    def test_zypper(self):
        self.assertEqual(pkgmgr._parse_zypper_remove(ZYPPER_REMOVE),
                         ["libexpat1", "python313-requests", "python313-urllib3"])
        self.assertEqual(pkgmgr._parse_zypper_table(ZYPPER_UNNEEDED), ["libfoo1", "python3-bar"])

    def test_apk(self):
        info = "alpine-baselayout-3.7.2-r1 - Alpine base dir structure\nca-certificates-bundle-20250911-r0 - Certs\n"
        pkgs = pkgmgr._parse_apk_info(info)
        self.assertEqual([(p['name'], p['version']) for p in pkgs],
                         [("alpine-baselayout", "3.7.2-r1"), ("ca-certificates-bundle", "20250911-r0")])
        self.assertEqual(pkgmgr._parse_apk_del("(1/2) Purging curl (8.23.0-r0)\n(2/2) Purging libcurl (8)\nOK: 8 MiB\n"),
                         ["curl", "libcurl"])

    def test_detect_order(self):
        with patch('shutil.which', side_effect=lambda t: t in ("dnf", "rpm", "zypper")):
            self.assertEqual(pkgmgr.detect(), "dnf")
        with patch('shutil.which', side_effect=lambda t: t == "apk"):
            self.assertEqual(pkgmgr.detect(), "apk")
        with patch('shutil.which', return_value=None):
            self.assertIsNone(pkgmgr.detect())

    def test_query_empty_is_none(self):
        with patch('subprocess.run', return_value=MagicMock(stdout=b"")):
            self.assertIsNone(pkgmgr.query(["x"], pkgmgr._parse_lines))
        with patch('subprocess.run', side_effect=OSError):
            self.assertIsNone(pkgmgr.query(["x"], pkgmgr._parse_lines))


class TestFlatpak(unittest.TestCase):
    def _un(self):
        un = PackageUninstaller(backend="pacman")
        un.flatpak = pkgmgr.FLATPAK
        return un

    @patch('subprocess.Popen')
    def test_lists_both_sources(self, mock_popen):
        outs = iter([(PACMAN_QI.encode(), None), (b"org.gimp.GIMP\t3.0.4\tGNU Image Manipulation Program\n", None)])
        mock_popen.return_value.communicate.side_effect = lambda: next(outs)
        pkgs = self._un().list_installed_packages()
        self.assertEqual({p['name']: p['source'] for p in pkgs},
                         {"git": "system", "niri": "system", "org.gimp.GIMP": "flatpak"})

    @patch('subprocess.run')
    def test_flatpak_uninstall_has_no_pkexec(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ok, msg = self._un().uninstall("org.gimp.GIMP", source="flatpak")
        self.assertTrue(ok)
        self.assertEqual(mock_run.call_args.args[0], ["flatpak", "uninstall", "-y", "--delete-data", "org.gimp.GIMP"])
        self.assertEqual(self._un().preview_removal("org.gimp.GIMP", "flatpak"), ["org.gimp.GIMP"])
