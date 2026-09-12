import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import tempfile


@dataclass
class RuntimeEnvironment:
    env: dict[str, str]
    storage: tempfile.TemporaryDirectory | None = None

    def close(self) -> None:
        if self.storage is not None:
            self.storage.cleanup()


def runtime_env(base_env: dict[str, str], captured: dict[str, str], work_dir: Path) -> dict[str, str]:
    env = captured.copy()
    # Nix's temporary build directory disappears when `nix develop` exits.
    for name in ("TMPDIR", "TMP", "TEMP", "TEMPDIR"):
        if name in base_env:
            env[name] = base_env[name]
        else:
            env.pop(name, None)
    # Keep the project Python first and preserve the built-in GPU library paths.
    for name, required in (
        ("PATH", str(work_dir / ".venv" / "bin")),
        ("LD_LIBRARY_PATH", base_env.get("LD_LIBRARY_PATH", "")),
    ):
        paths = [
            path for path in (required + os.pathsep + env.get(name, "")).split(os.pathsep)
            if path
        ]
        env[name] = os.pathsep.join(dict.fromkeys(paths))
    env["VIRTUAL_ENV"] = str(work_dir / ".venv")
    env["PWD"] = str(work_dir / "ComfyUI")
    return env


async def prepare_environment(
    work_dir: Path,
    base_env: dict[str, str],
    nix_bin: str,
    python_bin: str,
) -> RuntimeEnvironment:
    """Run shellHook before replacing the server; retain a GC root while it runs."""
    source = work_dir / "runtime"
    flake = source / "flake.nix"
    if not flake.exists() and not flake.is_symlink():
        return RuntimeEnvironment(base_env.copy())
    if not flake.is_file():
        raise RuntimeError(f"Runtime flake is not a readable file: {flake}")

    storage = tempfile.TemporaryDirectory(prefix="comfyui-environment-")
    process = None
    completed = False
    try:
        root = Path(storage.name)
        captured = root / "environment.json"
        process = await asyncio.create_subprocess_exec(
            nix_bin,
            "develop",
            f"path:{source}#default",
            "--profile",
            str(root / "profile"),
            "--command",
            python_bin,
            "-c",
            "import json, os, sys; "
            "open(sys.argv[1], 'w').write(json.dumps(dict(os.environ)))",
            str(captured),
            cwd=work_dir / "ComfyUI",
            env=base_env,
            start_new_session=True,
        )
        return_code = await process.wait()
        if return_code != 0:
            raise RuntimeError(f"Runtime flake failed (exit {return_code})")
        env = json.loads(captured.read_text())
        if not isinstance(env, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in env.items()
        ):
            raise RuntimeError("Runtime flake returned an invalid environment")
        captured.unlink()
        environment = RuntimeEnvironment(runtime_env(base_env, env, work_dir), storage)
        completed = True
        return environment
    finally:
        if not completed:
            if process is not None and process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
            storage.cleanup()
