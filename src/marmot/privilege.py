import subprocess


def run_root(cmd: list) -> tuple[bool, str, str]:
    """pkexec first, then passwordless sudo. Returns (ok, " (via sudo)" or "", stdout-or-error).
    Output is always captured: a text-mode polkit prompt must never write over the TUI."""
    err = ""
    for prefix, suffix in ((["pkexec"], ""), (["sudo", "-n"], " (via sudo)")):
        try:
            res = subprocess.run([*prefix, *cmd], check=True, capture_output=True)
            return True, suffix, res.stdout.decode("utf-8", errors="ignore").strip()
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode("utf-8", errors="ignore").strip() or str(e)
        except Exception as e:
            err = str(e)
    return False, "", err
