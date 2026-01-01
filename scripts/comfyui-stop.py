#!/usr/bin/env python3
import os
import signal
import sys
import time
from typing import Optional

WORK_DIR = os.path.expanduser("~/.config/comfyui")
PID_FILE = os.path.join(WORK_DIR, "comfyui.pid")


def read_pid() -> Optional[int]:
    if not os.path.exists(PID_FILE):
        return None
    with open(PID_FILE, "r", encoding="utf-8") as f:
        pid_str = f.read().strip()
    if pid_str.isdigit():
        return int(pid_str)
    os.remove(PID_FILE)
    return None


def stop_pid(pid: int) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
        for _ in range(50):
            time.sleep(0.1)
            os.kill(pid, 0)
        print("Process did not exit, sending SIGKILL...")
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except PermissionError:
        print("Permission denied when stopping process.")
        return False
    return True


def main() -> int:
    pid = read_pid()
    if pid is None:
        print("No running ComfyUI instance (pid file not found or invalid).")
        return 0

    success = stop_pid(pid)
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

    if success:
        print("ComfyUI stopped.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
