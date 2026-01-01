#!/usr/bin/env python3
import os
import subprocess
import sys
from typing import Dict

PYTHON_BIN = "__PYTHON_BIN__"  # patched by Nix
LIB_PATH = "__LIB_PATH__"  # patched by Nix
WORK_DIR = os.path.expanduser("~/.config/comfyui")
VENV_PATH = os.path.join(WORK_DIR, ".venv")

ENV_OVERRIDES: Dict[str, str] = {
    "WORK_DIR": WORK_DIR,
    "VENV_PATH": VENV_PATH,
    "ONEAPI_DEVICE_SELECTOR": "level_zero:gpu",
    "ZES_ENABLE_SYSMAN": "1",
    "NEOReadDebugKeys": "1",
    "OverrideDefaultFP64Settings": "1",
}


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
        print("Error: Virtual environment not found. Please run 'nix run .#run' first.")
        sys.exit(1)
    return python_bin


def ensure_repo() -> None:
    if not os.path.isdir(os.path.join(WORK_DIR, "ComfyUI")):
        print(f"Error: ComfyUI repository not found at {WORK_DIR}/ComfyUI")
        print("Please run 'nix run .#run' first to clone the repository.")
        sys.exit(1)


def main() -> int:
    env = env_with_venv()
    ensure_repo()
    ensure_venv(env)
    subprocess.run(
        ["git", "pull", "origin", "master"],
        check=True,
        env=env,
        cwd=os.path.join(WORK_DIR, "ComfyUI"),
    )
    print("Update completed successfully! (deps unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
