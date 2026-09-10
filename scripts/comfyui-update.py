#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

SETUP_BIN = "__SETUP_BIN__"
LIB_PATH = "__LIB_PATH__"

WORK_DIR = Path.home() / ".config" / "comfyui"
REPO_DIR = WORK_DIR / "ComfyUI"
VENV_PATH = WORK_DIR / ".venv"


ENV_OVERRIDES: Dict[str, str] = {
    "WORK_DIR": str(WORK_DIR),
    "VIRTUAL_ENV": str(VENV_PATH),
    # Intel XPU
    "ONEAPI_DEVICE_SELECTOR": "level_zero:gpu",
    "ZES_ENABLE_SYSMAN": "1",
    "NEOReadDebugKeys": "1",
    "IGC_EnableDPEmulation": "1",
    "OverrideDefaultFP64Settings": "1",
    # uv / ComfyUI Manager
    "UV_TORCH_BACKEND": "xpu",
    "UV_PYTHON_DOWNLOADS": "never",
}


def build_env() -> Dict[str, str]:
    env = os.environ.copy()
    env.update(ENV_OVERRIDES)

    env["LD_LIBRARY_PATH"] = f"{LIB_PATH}:" + env.get("LD_LIBRARY_PATH", "")

    env["PATH"] = str(VENV_PATH / "bin") + os.pathsep + env.get("PATH", "")

    return env


def check_repo() -> bool:
    if not REPO_DIR.exists():
        print(
            f"ComfyUI repository does not exist: {REPO_DIR}",
            file=sys.stderr,
        )
        print(
            "Run `comfyui-setup` first.",
            file=sys.stderr,
        )
        return False

    if not REPO_DIR.is_dir():
        print(
            f"ComfyUI repository path is not a directory: {REPO_DIR}",
            file=sys.stderr,
        )
        return False

    if not (REPO_DIR / ".git").exists():
        print(
            f"ComfyUI directory is not a Git repository: {REPO_DIR}",
            file=sys.stderr,
        )
        return False

    if not (REPO_DIR / "main.py").is_file():
        print(
            f"ComfyUI main.py is missing: {REPO_DIR}",
            file=sys.stderr,
        )
        return False

    return True


def run_git(
    *args: str,
    env: Dict[str, str],
    capture: bool = False,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "git",
            *args,
        ],
        cwd=REPO_DIR,
        env=env,
        check=True,
        text=True,
        stdout=(subprocess.PIPE if capture else None),
        stderr=(subprocess.PIPE if capture else None),
    )


def get_current_branch(
    env: Dict[str, str],
) -> str | None:
    result = subprocess.run(
        [
            "git",
            "symbolic-ref",
            "--quiet",
            "--short",
            "HEAD",
        ],
        cwd=REPO_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        return None

    branch = result.stdout.strip()

    return branch or None


def get_remote_default_branch(
    env: Dict[str, str],
) -> str:
    """
    Resolve origin's default branch from:

        refs/remotes/origin/HEAD -> refs/remotes/origin/master

    Falls back to master for ComfyUI.
    """
    result = subprocess.run(
        [
            "git",
            "symbolic-ref",
            "--quiet",
            "--short",
            "refs/remotes/origin/HEAD",
        ],
        cwd=REPO_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode == 0:
        value = result.stdout.strip()

        prefix = "origin/"

        if value.startswith(prefix):
            return value[len(prefix) :]

    return "master"


def worktree_is_clean(
    env: Dict[str, str],
) -> bool:
    result = run_git(
        "status",
        "--porcelain",
        env=env,
        capture=True,
    )

    return not result.stdout.strip()


def local_branch_exists(
    branch: str,
    env: Dict[str, str],
) -> bool:
    result = subprocess.run(
        [
            "git",
            "show-ref",
            "--verify",
            "--quiet",
            f"refs/heads/{branch}",
        ],
        cwd=REPO_DIR,
        env=env,
    )

    return result.returncode == 0


def update_repo(
    env: Dict[str, str],
) -> None:
    print("Updating ComfyUI repository...")

    #
    # Always update remote references first.
    #
    run_git(
        "fetch",
        "--prune",
        "origin",
        env=env,
    )

    current_branch = get_current_branch(env)

    #
    # Normal branch checkout
    #
    if current_branch is not None:
        print(f"Current branch: {current_branch}")

        run_git(
            "pull",
            "--ff-only",
            "origin",
            current_branch,
            env=env,
        )

        return

    #
    # Detached HEAD
    #
    target_branch = get_remote_default_branch(env)

    print("Repository is currently in detached HEAD state.")

    print(f"Target branch: {target_branch}")

    if not worktree_is_clean(env):
        raise RuntimeError(
            "ComfyUI has uncommitted changes while in detached "
            "HEAD state.\n"
            "Refusing to switch branches automatically.\n"
            "Commit, stash, or discard the changes first."
        )

    if local_branch_exists(
        target_branch,
        env,
    ):
        run_git(
            "switch",
            target_branch,
            env=env,
        )

    else:
        run_git(
            "switch",
            "--track",
            "-c",
            target_branch,
            f"origin/{target_branch}",
            env=env,
        )

    run_git(
        "pull",
        "--ff-only",
        "origin",
        target_branch,
        env=env,
    )


def sync_environment(
    env: Dict[str, str],
) -> None:
    print()
    print("Synchronizing ComfyUI environment...")

    subprocess.run(
        [
            SETUP_BIN,
        ],
        cwd=WORK_DIR,
        env=env,
        check=True,
    )


def main() -> int:
    if not check_repo():
        return 1

    env = build_env()

    try:
        update_repo(env)
        sync_environment(env)

    except subprocess.CalledProcessError as exc:
        print(
            f"Update failed with exit code {exc.returncode}.",
            file=sys.stderr,
        )
        return exc.returncode or 1

    except OSError as exc:
        print(
            f"Update failed: {exc}",
            file=sys.stderr,
        )
        return 1

    print()
    print("ComfyUI update completed successfully.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
