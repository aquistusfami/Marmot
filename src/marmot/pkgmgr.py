"""Package manager backends (apt, pacman). Each backend is plain data + small parsers."""
import shutil
from pathlib import Path


def _parse_dpkg(out: str) -> list:
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


def _parse_apt_sim(out: str) -> list:
    # `apt-get -s purge` prints one "Purg <pkg> [...]" line per package it would remove
    return [ln.split()[1] for ln in out.splitlines() if ln.startswith(("Purg ", "Remv "))]


def _parse_lines(out: str) -> list:
    return [ln.split()[0] for ln in out.splitlines() if ln.strip()]


BACKENDS = {
    'apt': {
        'label': "Apt",
        'list_cmd': ["dpkg-query", "-W", "-f=${Package}\t${Version}\t${binary:Summary}\n"],
        'parse_list': _parse_dpkg,
        'preview_cmd': lambda p: ["apt-get", "-s", "purge", p],
        'parse_preview': _parse_apt_sim,
        'remove_cmd': lambda p: ["apt-get", "purge", "-y", p],
        'cache_dir': Path("/var/cache/apt/archives"),
        'cache_glob': "*.deb",
        'clean_cmd': lambda: ["apt-get", "clean"],
    },
    'pacman': {
        'label': "Pacman",
        'list_cmd': ["pacman", "-Qi"],
        'parse_list': _parse_pacman_qi,
        # -p only prints the transaction (no root, no changes); pacman rejects -n together with -p
        'preview_cmd': lambda p: ["pacman", "-Rsp", "--print-format", "%n", p],
        'parse_preview': _parse_lines,
        'remove_cmd': lambda p: ["pacman", "-Rns", "--noconfirm", p],
        'cache_dir': Path("/var/cache/pacman/pkg"),
        'cache_glob': "*.pkg.tar.*",
        # keep the newest version of each package so downgrades stay possible
        'clean_cmd': lambda: ["paccache", "-rk1"] if shutil.which("paccache") else ["pacman", "-Sc", "--noconfirm"],
    },
}


def detect() -> str | None:
    if shutil.which("dpkg-query") and shutil.which("apt-get"):
        return 'apt'
    if shutil.which("pacman"):
        return 'pacman'
    return None


def get(name: str | None = None) -> dict | None:
    """Backend dict for `name`, or the detected one; None when the distro is unsupported."""
    return BACKENDS.get(name or detect() or "")

