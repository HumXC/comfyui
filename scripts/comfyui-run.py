#!/usr/bin/env python3
import os
import subprocess
import sys
import time
import webbrowser
import threading
import urllib.error
import urllib.request
from typing import Dict, Optional

PYTHON_BIN = "__PYTHON_BIN__"  # patched by Nix
LIB_PATH = "__LIB_PATH__"  # patched by Nix
WORK_DIR = os.path.expanduser("~/.config/comfyui")
VENV_PATH = os.path.join(WORK_DIR, ".venv")
PID_FILE = os.path.join(WORK_DIR, "comfyui.pid")
DEPS_STAMP = os.path.join(WORK_DIR, ".deps_stamp")

ENV_OVERRIDES: Dict[str, str] = {
    "WORK_DIR": WORK_DIR,
    "VENV_PATH": VENV_PATH,
    "ONEAPI_DEVICE_SELECTOR": "level_zero:gpu",
    "ZES_ENABLE_SYSMAN": "1",
    "NEOReadDebugKeys": "1",
    "IGC_EnableDPEmulation": "1",
    "OverrideDefaultFP64Settings": "1",
}
from dotenv import load_dotenv

load_dotenv(os.path.join(WORK_DIR, ".env"))


def ensure_dirs() -> None:
    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(VENV_PATH, exist_ok=True)


def env_with_venv() -> Dict[str, str]:
    env = os.environ.copy()
    env.update(ENV_OVERRIDES)
    env["LD_LIBRARY_PATH"] = f"{LIB_PATH}:" + env.get("LD_LIBRARY_PATH", "")
    env["VIRTUAL_ENV"] = VENV_PATH
    env["PATH"] = os.path.join(VENV_PATH, "bin") + os.pathsep + env.get("PATH", "")
    return env


def ensure_venv(env: Dict[str, str]) -> str:
    python_bin = os.path.join(VENV_PATH, "bin", "python")
    if not os.path.exists(python_bin):
        print(f"Creating virtual environment at {VENV_PATH}...")
        subprocess.run([PYTHON_BIN, "-m", "venv", VENV_PATH], check=True, env=env)
    return python_bin


def ensure_repo(env: Dict[str, str]) -> None:
    if not os.path.isdir(os.path.join(WORK_DIR, "ComfyUI")):
        print(f"Cloning ComfyUI repository to {WORK_DIR}/ComfyUI...")
        subprocess.run(
            [
                "git",
                "clone",
                "https://github.com/comfyanonymous/ComfyUI.git",
                "ComfyUI",
            ],
            check=True,
            env=env,
            cwd=WORK_DIR,
        )


def install_deps(env: Dict[str, str]) -> None:
    pip_bin = os.path.join(VENV_PATH, "bin", "pip")
    subprocess.run(
        [
            pip_bin,
            "install",
            "torch",
            "torchvision",
            "torchaudio",
            "--index-url",
            "https://download.pytorch.org/whl/xpu",
        ],
        check=True,
        env=env,
        cwd=WORK_DIR,
    )
    req = os.path.join(WORK_DIR, "ComfyUI", "requirements.txt")
    mgr = os.path.join(WORK_DIR, "ComfyUI", "manager_requirements.txt")
    if os.path.exists(req):
        subprocess.run(
            [pip_bin, "install", "-r", req], check=True, env=env, cwd=WORK_DIR
        )
    if os.path.exists(mgr):
        subprocess.run(
            [pip_bin, "install", "-r", mgr], check=True, env=env, cwd=WORK_DIR
        )
    with open(DEPS_STAMP, "w", encoding="utf-8") as f:
        f.write("installed")


def deps_needed() -> bool:
    return not os.path.exists(DEPS_STAMP)


def write_pid(pid: int) -> None:
    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(pid))


def read_pid() -> Optional[int]:
    if not os.path.exists(PID_FILE):
        return None
    with open(PID_FILE, "r", encoding="utf-8") as f:
        pid_str = f.read().strip()
    if pid_str.isdigit():
        return int(pid_str)
    os.remove(PID_FILE)
    return None


def is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _is_url_up(url: str, timeout: float = 1.0) -> bool:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 500
    except (urllib.error.URLError, TimeoutError):
        return False


def open_browser_when_ready(
    url: str = "http://127.0.0.1:8188", timeout: float = 10.0
) -> None:
    def _wait_and_open() -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _is_url_up(url):
                webbrowser.open(url)
                return
            time.sleep(0.5)
        print(
            "ComfyUI UI did not respond within 10s; server may still be starting or failed."
        )

    threading.Thread(target=_wait_and_open, daemon=True).start()


def open_browser_now(url: str = "http://127.0.0.1:8188") -> None:
    try:
        webbrowser.open(url)
    except Exception:
        # Fallback: just print the URL if opening fails (headless setups)
        print(f"Open UI at {url}")


def main() -> int:
    ensure_dirs()
    env = env_with_venv()
    python_bin = ensure_venv(env)
    ensure_repo(env)

    existing_pid = read_pid()
    if existing_pid and is_process_alive(existing_pid):
        print(f"ComfyUI already running (pid {existing_pid}), opening UI...")
        open_browser_now()
        open_browser_when_ready()
        return 0
    if existing_pid and not is_process_alive(existing_pid):
        os.remove(PID_FILE)

    if deps_needed():
        install_deps(env)

    print("Running ComfyUI...")
    proc = subprocess.Popen([python_bin, "ComfyUI/main.py"], env=env, cwd=WORK_DIR)
    write_pid(proc.pid)
    open_browser_when_ready()
    try:
        proc.wait()
    finally:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
