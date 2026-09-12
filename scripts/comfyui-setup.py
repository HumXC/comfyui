#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict

PYTHON_BIN = "__PYTHON_BIN__"  # patched by Nix
UV_BIN = "__UV_BIN__"  # patched by Nix
LIB_PATH = "__LIB_PATH__"  # patched by Nix
RUNTIME_TEMPLATE = "__RUNTIME_TEMPLATE__"

WORK_DIR = Path.home() / ".config" / "comfyui"
REPO_DIR = WORK_DIR / "ComfyUI"
VENV_PATH = WORK_DIR / ".venv"
VENV_PYTHON = VENV_PATH / "bin" / "python"

DEPS_STAMP = WORK_DIR / ".deps_stamp"

COMFYUI_REPO = "https://github.com/Comfy-Org/ComfyUI.git"

TORCH_VERSION = "__TORCH_VERSION__"
TORCHVISION_VERSION = "__TORCHVISION_VERSION__"

CONSTRAINTS_PATH = WORK_DIR / "constraints.txt"

UV_WRAPPER_PATH = WORK_DIR / "uv"

# 修改 Torch 固定策略时，同时修改这个值。
# 这样旧环境会自动被识别为需要重新 setup。
TORCH_POLICY_VERSION = "xpu-v1"

ENV_OVERRIDES: Dict[str, str] = {
    "WORK_DIR": str(WORK_DIR),
    "VIRTUAL_ENV": str(VENV_PATH),
    # Intel XPU
    "ONEAPI_DEVICE_SELECTOR": "level_zero:gpu",
    "ZES_ENABLE_SYSMAN": "1",
    "NEOReadDebugKeys": "1",
    "IGC_EnableDPEmulation": "1",
    "OverrideDefaultFP64Settings": "1",
    # uv
    "UV_TORCH_BACKEND": "xpu",
    "UV_PYTHON_DOWNLOADS": "never",
    "UV_CONSTRAINT": str(CONSTRAINTS_PATH),
}


def expected_uv_wrapper() -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

export VIRTUAL_ENV="{VENV_PATH}"
export UV_CONSTRAINT="{CONSTRAINTS_PATH}"
export UV_TORCH_BACKEND="xpu"
export UV_PYTHON_DOWNLOADS="never"

exec "{UV_BIN}" "$@"
"""


def ensure_uv_wrapper() -> None:
    expected = expected_uv_wrapper()

    try:
        current = UV_WRAPPER_PATH.read_text(
            encoding="utf-8",
        )
    except FileNotFoundError:
        current = None

    if current != expected:
        UV_WRAPPER_PATH.write_text(
            expected,
            encoding="utf-8",
        )

        print(f"Updated uv wrapper: {UV_WRAPPER_PATH}")
    else:
        print("uv wrapper: OK")

    UV_WRAPPER_PATH.chmod(0o755)


def expected_constraints() -> str:
    return f"torch=={TORCH_VERSION}\n" f"torchvision=={TORCHVISION_VERSION}\n"


def ensure_constraints() -> bool:
    """
    Ensure constraints.txt matches the versions injected by Nix.

    Returns True if the file was created or changed.
    """
    expected = expected_constraints()

    try:
        current = CONSTRAINTS_PATH.read_text(
            encoding="utf-8",
        )
    except FileNotFoundError:
        current = None

    if current == expected:
        print("Python constraints: OK")
        return False

    CONSTRAINTS_PATH.write_text(
        expected,
        encoding="utf-8",
    )

    print(f"Updated Python constraints: {CONSTRAINTS_PATH}")

    return True


def build_env() -> Dict[str, str]:
    env = os.environ.copy()

    env.update(ENV_OVERRIDES)

    env["LD_LIBRARY_PATH"] = f"{LIB_PATH}:" + env.get("LD_LIBRARY_PATH", "")

    env["PATH"] = str(VENV_PATH / "bin") + os.pathsep + env.get("PATH", "")

    return env


def hash_file(path: Path) -> str | None:
    if not path.is_file():
        return None

    digest = hashlib.sha256()

    with path.open("rb") as f:
        while chunk := f.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def expected_deps_state() -> dict:
    return {
        "python": PYTHON_BIN,
        "constraints": hash_file(CONSTRAINTS_PATH),
        "requirements": hash_file(REPO_DIR / "requirements.txt"),
        "manager_requirements": hash_file(REPO_DIR / "manager_requirements.txt"),
    }


def read_deps_state() -> dict | None:
    try:
        with DEPS_STAMP.open(
            "r",
            encoding="utf-8",
        ) as f:
            value = json.load(f)

        if isinstance(value, dict):
            return value

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
    ):
        pass

    return None


def write_deps_state() -> None:
    state = expected_deps_state()

    with DEPS_STAMP.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            state,
            f,
            indent=2,
            sort_keys=True,
        )

        f.write("\n")


def check_repo() -> tuple[bool, str | None]:
    if not REPO_DIR.exists():
        return False, "ComfyUI repository is missing"

    if not REPO_DIR.is_dir():
        return False, f"{REPO_DIR} is not a directory"

    git_dir = REPO_DIR / ".git"

    if not git_dir.exists():
        return False, f"{REPO_DIR} is not a Git repository"

    main_py = REPO_DIR / "main.py"

    if not main_py.is_file():
        return False, "ComfyUI main.py is missing"

    return True, None


def check_venv() -> tuple[bool, str | None]:
    if not VENV_PATH.exists():
        return False, "Python virtual environment is missing"

    if not VENV_PATH.is_dir():
        return False, f"{VENV_PATH} is not a directory"

    if not VENV_PYTHON.exists():
        return False, "Virtual environment Python is missing"

    try:
        result = subprocess.run(
            [
                str(VENV_PYTHON),
                "-c",
                ("import sys; " "print(sys.executable); " "print(sys.version)"),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "Virtual environment Python is broken"

    if result.returncode != 0:
        return False, "Virtual environment Python cannot run"

    return True, None


def check_deps() -> tuple[bool, str | None]:
    if not DEPS_STAMP.exists():
        return False, "Python dependencies have not been initialized"

    actual = read_deps_state()

    if actual is None:
        return False, "Dependency state file is invalid"

    expected = expected_deps_state()

    if actual != expected:
        return False, "Python dependency state is outdated"

    # 至少确认最关键的 torch 还能正常 import。
    env = build_env()

    try:
        result = subprocess.run(
            [
                str(VENV_PYTHON),
                "-c",
                "import torch",
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "PyTorch installation is broken"

    if result.returncode != 0:
        return False, "PyTorch cannot be imported"

    return True, None


def check_environment() -> list[str]:
    errors: list[str] = []

    repo_ok, repo_error = check_repo()

    if not repo_ok:
        if repo_error:
            errors.append(repo_error)

        # 没仓库就无法计算 requirements 状态。
        return errors

    venv_ok, venv_error = check_venv()

    if not venv_ok:
        if venv_error:
            errors.append(venv_error)

        return errors

    deps_ok, deps_error = check_deps()

    if not deps_ok and deps_error:
        errors.append(deps_error)

    return errors


def ensure_work_dir() -> None:
    WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def ensure_repo(env: Dict[str, str]) -> None:
    ok, error = check_repo()

    if ok:
        print("ComfyUI repository: OK")
        return

    if REPO_DIR.exists():
        raise RuntimeError(
            f"{error}\n" f"Refusing to overwrite existing path: {REPO_DIR}"
        )

    print("ComfyUI repository not found.")
    print(f"Cloning into {REPO_DIR}...")

    subprocess.run(
        [
            "git",
            "clone",
            COMFYUI_REPO,
            str(REPO_DIR),
        ],
        check=True,
        env=env,
        cwd=WORK_DIR,
    )


def remove_venv() -> None:
    if not VENV_PATH.exists():
        return

    print(f"Removing broken virtual environment: {VENV_PATH}")

    shutil.rmtree(VENV_PATH)


def create_venv(env: Dict[str, str]) -> None:
    print(f"Creating virtual environment at {VENV_PATH}...")

    subprocess.run(
        [
            UV_BIN,
            "venv",
            str(VENV_PATH),
            "--python",
            PYTHON_BIN,
            "--no-python-downloads",
        ],
        check=True,
        env=env,
        cwd=WORK_DIR,
    )


def ensure_venv(
    env: Dict[str, str],
) -> bool:
    """
    Returns True if a new venv was created.
    """

    ok, _ = check_venv()

    if ok:
        print("Python virtual environment: OK")
        return False

    if VENV_PATH.exists():
        remove_venv()

    create_venv(env)

    ok, error = check_venv()

    if not ok:
        raise RuntimeError(error or "Failed to create virtual environment")

    return True


def uv_pip_install(
    env: Dict[str, str],
    *args: str,
) -> None:
    subprocess.run(
        [
            UV_BIN,
            "pip",
            "install",
            "--python",
            str(VENV_PYTHON),
            *args,
        ],
        check=True,
        env=env,
        cwd=REPO_DIR,
    )


def install_deps(
    env: Dict[str, str],
) -> None:
    print("Installing Intel XPU PyTorch...")

    uv_pip_install(
        env,
        "torch",
        "torchvision",
    )

    requirements = REPO_DIR / "requirements.txt"

    if requirements.is_file():
        print("Installing ComfyUI dependencies...")

        uv_pip_install(
            env,
            "-r",
            str(requirements),
        )

    manager_requirements = REPO_DIR / "manager_requirements.txt"

    if manager_requirements.is_file():
        print("Installing ComfyUI Manager dependencies...")

        uv_pip_install(
            env,
            "-r",
            str(manager_requirements),
        )

    write_deps_state()


def ensure_deps(
    env: Dict[str, str],
    venv_created: bool,
    constraints_changed: bool,
) -> None:
    if not venv_created and not constraints_changed:
        ok, _ = check_deps()

        if ok:
            print("Python dependencies: OK")
            return

    print("Python dependencies need synchronization.")

    install_deps(env)

    ok, error = check_deps()

    if not ok:
        raise RuntimeError(error or "Dependency installation failed")


def ensure_runtime_configuration() -> None:
    runtime = WORK_DIR / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    example = runtime / "flake.nix.example"
    if not example.exists() and not example.is_symlink():
        template = Path(RUNTIME_TEMPLATE).read_text()
        with example.open("x") as output:
            output.write(template)
    print(f"Runtime environment example: {example}")


def setup() -> None:
    ensure_work_dir()
    ensure_runtime_configuration()

    constraints_changed = ensure_constraints()

    ensure_constraints()
    ensure_uv_wrapper()

    env = build_env()

    ensure_repo(env)

    venv_created = ensure_venv(env)

    ensure_deps(
        env,
        venv_created=venv_created,
        constraints_changed=constraints_changed,
    )

    print()
    print("ComfyUI environment is ready.")


def check_only() -> int:
    errors = check_environment()

    if not errors:
        return 0

    for error in errors:
        print(
            f"Environment error: {error}",
            file=sys.stderr,
        )

    return 1


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--check",
        action="store_true",
        help="Check the environment without modifying it",
    )

    args = parser.parse_args()

    if args.check:
        return check_only()

    try:
        setup()
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            f"Setup failed: {exc}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
