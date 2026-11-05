"""Package manager backends. Each backend is plain data + small output parsers.

Keys every backend has:
  label, list_cmd/parse_list, preview_cmd/parse_preview, remove_cmd, privileged,
  cache_dir/cache_glob/clean_cmd (cache_dir None = no package cache to clean),
  orphans_cmd/parse_orphans/remove_orphans_cmd (orphans_cmd None = not supported).
"""
import shutil
import subprocess
from pathlib import Path


def _parse_tabbed(out: str) -> list:
    """`name<TAB>version<TAB>summary` lines (dpkg-query, rpm --qf, flatpak --columns)."""
    pkgs = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0]:
            pkgs.append({'name': parts[0], 'version': parts[1], 'summary': parts[2]})
    return pkgs


def _parse_pacman_qi(out: str) -> list:
    """Parse `pacman -Qi` output (blank-line separated blocks of `Key : Value`)."""
    pkgs = []
    for block in out.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, sep, val = line.partition(":")
            if sep and not line.startswith(" "):
                fields[key.strip()] = val.strip()
        if fields.get("Name"):
            pkgs.append({'name': fields["Name"], 'version': fields.get("Version", ""),
                         'summary': fields.get("Description", "")})
    return pkgs


def _parse_apk_info(out: str) -> list:
    """`apk info -vv`: `name-1.2.3-r0 - description`."""
    pkgs = []
    for line in out.splitlines():
        nv, sep, desc = line.partition(" - ")
        parts = nv.rsplit("-", 2)
        if sep and len(parts) == 3:
            pkgs.append({'name': parts[0], 'version': f"{parts[1]}-{parts[2]}", 'summary': desc})
    return pkgs


def _parse_apt_sim(out: str) -> list:
    # `apt-get -s purge|autoremove` prints one "Purg <pkg> [...]" / "Remv <pkg>" line per removed package
    return [ln.split()[1] for ln in out.splitlines() if ln.startswith(("Purg ", "Remv "))]


def _parse_lines(out: str) -> list:
    return [ln.split()[0] for ln in out.splitlines() if ln.strip()]


def _parse_dnf_remove(out: str) -> list:
    """`dnf remove --assumeno`: package rows (leading space, >=5 columns) under the "Removing..." headers."""
    names, on = [], False
    for ln in out.splitlines():
        if ln.startswith("Transaction Summary"):
            break
        if ln.startswith("Removing"):
            on = True
        elif on and ln.startswith(" ") and len(ln.split()) >= 5:
            names.append(ln.split()[0])
    return names


def _parse_zypper_remove(out: str) -> list:
    """`zypper rm --dry-run`: indented, space separated names after "...going to be REMOVED:"."""
    names, on = [], False
    for ln in out.splitlines():
        if "going to be REMOVED:" in ln:
            on = True
        elif on:
            if not ln.strip():
                break
            names.extend(ln.split())
    return names


def _parse_zypper_table(out: str) -> list:
    """`zypper packages --unneeded`: `S | Repository | Name | Version | Arch` rows."""
    rows = [[c.strip() for c in ln.split("|")] for ln in out.splitlines() if ln.count("|") >= 4]
    return [r[2] for r in rows if r[2] and r[2] != "Name"]


def _parse_apk_del(out: str) -> list:
    # `apk del --simulate`: "(1/9) Purging curl (8.23.0-r0)"
    return [ln.split()[2] for ln in out.splitlines() if ln.startswith("(") and len(ln.split()) >= 3]


def _first_existing(*paths: str) -> Path:
    return next((Path(p) for p in paths if Path(p).exists()), Path(paths[0]))


_RPM_LIST = ["rpm", "-qa", "--qf", "%{NAME}\t%{VERSION}-%{RELEASE}\t%{SUMMARY}\n"]

BACKENDS = {
    'apt': {
        'label': "Apt",
        'list_cmd': ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${binary:Summary}\n"],
        'parse_list': _parse_tabbed,
        'preview_cmd': lambda p: ["apt-get", "-s", "purge", p],
        'parse_preview': _parse_apt_sim,
        'remove_cmd': lambda p: ["apt-get", "purge", "-y", p],
        'privileged': True,
        'cache_dir': Path("/var/cache/apt/archives"),
        'cache_glob': "*.deb",
        'clean_cmd': lambda: ["apt-get", "clean"],
        'orphans_cmd': ["apt-get", "-s", "autoremove"],
        'parse_orphans': _parse_apt_sim,
        'remove_orphans_cmd': lambda names: ["apt-get", "autoremove", "--purge", "-y"],
    },
    'pacman': {
        'label': "Pacman",
        'list_cmd': ["pacman", "-Qi"],
        'parse_list': _parse_pacman_qi,
        # -p only prints the transaction (no root, no changes); pacman rejects -n together with -p
        'preview_cmd': lambda p: ["pacman", "-Rsp", "--print-format", "%n", p],
        'parse_preview': _parse_lines,
        'remove_cmd': lambda p: ["pacman", "-Rns", "--noconfirm", p],
        'privileged': True,
        'cache_dir': Path("/var/cache/pacman/pkg"),
        'cache_glob': "*.pkg.tar.*",
        # keep the newest version of each package so downgrades stay possible
        'clean_cmd': lambda: ["paccache", "-rk1"] if shutil.which("paccache") else ["pacman", "-Sc", "--noconfirm"],
        'orphans_cmd': ["pacman", "-Qdtq"],
        'parse_orphans': _parse_lines,
        'remove_orphans_cmd': lambda names: ["pacman", "-Rns", "--noconfirm", *names],
    },
    'dnf': {
        'label': "DNF",
        'list_cmd': _RPM_LIST,
        'parse_list': _parse_tabbed,
        'preview_cmd': lambda p: ["dnf", "remove", "--assumeno", p],
        'parse_preview': _parse_dnf_remove,
        'remove_cmd': lambda p: ["dnf", "remove", "-y", p],
        'privileged': True,
        'cache_dir': _first_existing("/var/cache/libdnf5", "/var/cache/dnf"),
        'cache_glob': "**/*.rpm",
        'clean_cmd': lambda: ["dnf", "clean", "packages"],
        'orphans_cmd': ["dnf", "repoquery", "--unneeded", "--qf", "%{name}\n"],
        'parse_orphans': _parse_lines,
        'remove_orphans_cmd': lambda names: ["dnf", "autoremove", "-y"],
    },
    'zypper': {
        'label': "Zypper",
        'list_cmd': _RPM_LIST,
        'parse_list': _parse_tabbed,
        'preview_cmd': lambda p: ["zypper", "--non-interactive", "rm", "--dry-run", "--clean-deps", p],
        'parse_preview': _parse_zypper_remove,
        'remove_cmd': lambda p: ["zypper", "--non-interactive", "rm", "--clean-deps", p],
        'privileged': True,
        'cache_dir': Path("/var/cache/zypp/packages"),
        'cache_glob': "**/*.rpm",
        'clean_cmd': lambda: ["zypper", "clean"],
        'orphans_cmd': ["zypper", "--quiet", "--non-interactive", "packages", "--unneeded"],
        'parse_orphans': _parse_zypper_table,
        'remove_orphans_cmd': lambda names: ["zypper", "--non-interactive", "rm", "--clean-deps", *names],
    },
    'apk': {
        'label': "APK",
        'list_cmd': ["apk", "info", "-vv"],
        'parse_list': _parse_apk_info,
        'preview_cmd': lambda p: ["apk", "del", "--simulate", p],
        'parse_preview': _parse_apk_del,
        'remove_cmd': lambda p: ["apk", "del", p],
        'privileged': True,
        # apk only keeps a package cache when /etc/apk/cache is configured; apk del already drops orphans
        'cache_dir': Path("/etc/apk/cache") if Path("/etc/apk/cache").is_dir() else None,
        'cache_glob': "*.apk",
        'clean_cmd': lambda: ["apk", "cache", "clean"],
        'orphans_cmd': None,
    },
}

# Flatpak apps sit beside the distro backend; flatpak asks polkit itself for system installs.
FLATPAK = {
    'label': "Flatpak",
    'list_cmd': ["flatpak", "list", "--app", "--columns=application,version,name"],
    'parse_list': _parse_tabbed,
    'preview_cmd': None,  # removing an app never takes other apps with it
    'remove_cmd': lambda app_id: ["flatpak", "uninstall", "-y", "--delete-data", app_id],
    'privileged': False,
}

# Detection order matters: dnf before zypper (some systems ship both rpm tools).
_DETECT = [('apt', ("dpkg-query", "apt-get")), ('pacman', ("pacman",)), ('dnf', ("dnf", "rpm")),
           ('zypper', ("zypper", "rpm")), ('apk', ("apk",))]


def detect() -> str | None:
    for name, tools in _DETECT:
        if all(shutil.which(t) for t in tools):
            return name
    return None


def get(name: str | None = None) -> dict | None:
    """Backend dict for `name`, or the detected one; None when the distro is unsupported."""
    return BACKENDS.get(name or detect() or "")


def flatpak() -> dict | None:
    return FLATPAK if shutil.which("flatpak") else None


def query(cmd: list, parser) -> list | None:
    """Run a read-only command and parse its stdout; None when it cannot run or yields nothing."""
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return parser(res.stdout.decode("utf-8", errors="ignore")) or None
