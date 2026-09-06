"""ابزار مشترک مدیریت فرآیندهای کپچر."""

import subprocess
from typing import Optional


def terminate_process(proc: Optional[subprocess.Popen], timeout: float = 5.0) -> None:
    """فرآیند را با terminate و در صورت نیاز kill متوقف می‌کند."""
    if not proc:
        return
    try:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    finally:
        for stream in (proc.stdout, proc.stderr, proc.stdin):
            if stream:
                try:
                    stream.close()
                except Exception:
                    pass


def process_is_alive(proc: Optional[subprocess.Popen]) -> bool:
    return bool(proc and proc.poll() is None)


def ensure_process_started(proc: subprocess.Popen, grace_seconds: float = 0.4) -> str:
    """
    کمی صبر می‌کند؛ اگر فرآیند زود مرد، stderr را برمی‌گرداند (خالی یعنی زنده است).
    """
    import time
    time.sleep(grace_seconds)
    if proc.poll() is None:
        return ""
    err = ""
    try:
        if proc.stderr:
            err = (proc.stderr.read() or "").strip()
    except Exception:
        pass
    return err or f"exit code {proc.returncode}"
