#!/usr/bin/env python3
import asyncio
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


environment_module = load_module("runtime_environment", "runtime_environment.py")
prepare_environment = environment_module.prepare_environment
runtime_env = environment_module.runtime_env
launcher_module = load_module("comfyui_launcher_test", "comfyui-run.py")
setup_module = load_module("comfyui_setup_test", "comfyui-setup.py")


class SetupTests(unittest.TestCase):
    def test_initialization_preserves_edits_and_does_not_create_git(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            template = work / "template.nix"
            template.write_text("initial")
            with patch.multiple(setup_module, WORK_DIR=work, RUNTIME_TEMPLATE=str(template)):
                setup_module.ensure_runtime_configuration()
                example = work / "runtime/flake.nix.example"
                self.assertFalse((work / "flake.nix").exists())
                self.assertFalse((work / "runtime/flake.nix").exists())
                self.assertEqual(example.read_text(), "initial")
                example.write_text("user edit")
                setup_module.ensure_runtime_configuration()
                self.assertEqual(example.read_text(), "user edit")
                self.assertFalse((work / "runtime/flake.nix").exists())
                self.assertFalse((work / ".git").exists())

    def test_setup_preserves_enabled_environment_and_leaves_disabled_environment_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            runtime = work / "runtime"
            runtime.mkdir()
            flake = runtime / "flake.nix"
            flake.write_text("user configuration")
            template = work / "template.nix"
            template.write_text("example")
            with patch.multiple(setup_module, WORK_DIR=work, RUNTIME_TEMPLATE=str(template)):
                setup_module.ensure_runtime_configuration()
                self.assertEqual(flake.read_text(), "user configuration")
                flake.unlink()
                setup_module.ensure_runtime_configuration()
                self.assertFalse(flake.exists())
                self.assertEqual((runtime / "flake.nix.example").read_text(), "example")

    def test_menu_opens_example_until_enabled(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            runtime = work / "runtime"
            runtime.mkdir()
            example = runtime / "flake.nix.example"
            example.write_text("example")
            with patch.object(launcher_module, "WORK_DIR", work), patch.object(
                launcher_module.subprocess, "Popen"
            ) as popen:
                launcher_module.ComfyUILauncher.open_runtime_environment(None)
                self.assertEqual(popen.call_args.args[0][-1], str(example))
                flake = runtime / "flake.nix"
                flake.write_text("enabled")
                launcher_module.ComfyUILauncher.open_runtime_environment(None)
                self.assertEqual(popen.call_args.args[0][-1], str(flake))

    def test_missing_flake_skips_nix_even_with_example_and_top_level_file(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / "runtime").mkdir()
            (work / "runtime/flake.nix.example").write_text("example")
            (work / "flake.nix").write_text("ignored")
            with patch.object(environment_module.asyncio, "create_subprocess_exec") as spawn:
                result = asyncio.run(prepare_environment(work, {"BASE": "yes"}, "unused", "unused"))
            spawn.assert_not_called()
            self.assertEqual(result.env, {"BASE": "yes"})
            self.assertIsNone(result.storage)


    def test_runtime_env_keeps_venv_libraries_and_valid_temp(self):
        env = runtime_env(
            {"LD_LIBRARY_PATH": "/gpu", "TMPDIR": "/tmp"},
            {"PATH": "/tools", "LD_LIBRARY_PATH": "/extra", "TMPDIR": "/gone"},
            Path("/work"),
        )
        self.assertEqual(env["PATH"], "/work/.venv/bin:/tools")
        self.assertEqual(env["LD_LIBRARY_PATH"], "/gpu:/extra")
        self.assertEqual(env["TMPDIR"], "/tmp")
        self.assertEqual(env["VIRTUAL_ENV"], "/work/.venv")


@unittest.skipUnless(os.environ.get("COMFYUI_TEST_NIXPKGS"), "requires local nixpkgs source")
class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.storage = tempfile.TemporaryDirectory(prefix="comfyui-test-")
        self.work = Path(self.storage.name)
        self.runtime_dir = self.work / "runtime"
        self.runtime_dir.mkdir()
        self.repo = self.work / "ComfyUI"
        self.repo.mkdir()
        self.venv = self.work / ".venv"
        (self.venv / "bin").mkdir(parents=True)
        (self.venv / "bin" / "python").symlink_to(sys.executable)
        self.nix = shutil.which("nix")
        self.base = os.environ.copy()
        self.base["WORK_DIR"] = str(self.work)
        self.base.pop("HOOK_REMOVED", None)
        self.write_flake('export HOOK_VERSION="one"; export HOOK_REMOVED="old"')
        self.launcher = None
        self.patchers = []

    async def asyncTearDown(self):
        if self.launcher is not None:
            await self.launcher.shutdown()
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.storage.cleanup()

    def write_flake(self, hook):
        (self.runtime_dir / "settings.nix").write_text("{ name = \"relative-import\"; }")
        nixpkgs = os.environ["COMFYUI_TEST_NIXPKGS"]
        (self.runtime_dir / "flake.nix").write_text('''{
  inputs.nixpkgs.url = "path:''' + nixpkgs + '''";
  outputs = {nixpkgs, ...}: {
    devShells = nixpkgs.lib.genAttrs ["x86_64-linux" "aarch64-linux"] (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      settings = import ./settings.nix;
    in {
      default = pkgs.mkShell {
        RELATIVE_IMPORT = settings.name;
        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [pkgs.libxcb];
        shellHook = \'\'
          echo "hook output remains separate from the environment capture"
          ''' + hook + '''
        \'\';
      };
    });
  };
}
''')

    async def prepare(self):
        return await prepare_environment(self.work, self.base, self.nix, sys.executable)

    def make_launcher(self):
        patcher = patch.multiple(
            launcher_module, WORK_DIR=self.work, REPO_DIR=self.repo,
            VENV_PATH=self.venv, VENV_PYTHON=self.venv / "bin" / "python",
            PID_FILE=self.work / "comfyui.pid", LAUNCHER_PID_FILE=self.work / "launcher.pid",
            NIX_BIN=self.nix,
        )
        patcher.start()
        self.patchers.append(patcher)
        with patch.object(launcher_module.ComfyUILauncher, "load_icon", return_value=b""):
            self.launcher = launcher_module.ComfyUILauncher()
        self.launcher.build_env = lambda: self.base.copy()
        (self.repo / "main.py").write_text(
            "import os, pathlib, time\n"
            "pathlib.Path(os.environ['WORK_DIR'], 'child-' + str(os.getpid())).write_text("
            "os.environ.get('HOOK_VERSION', 'none'))\n"
            "time.sleep(120)\n"
        )
        return self.launcher

    async def wait_for_file(self, path):
        async with asyncio.timeout(30):
            while not path.exists():
                await asyncio.sleep(0.02)

    async def test_hook_relative_import_library_reload_and_disable(self):
        first = await self.prepare()
        try:
            self.assertEqual(first.env["HOOK_VERSION"], "one")
            self.assertEqual(first.env["RELATIVE_IMPORT"], "relative-import")
            child = await asyncio.create_subprocess_exec(
                sys.executable, "-c", "import ctypes; ctypes.CDLL('libxcb.so.1')",
                env=first.env,
            )
            self.assertEqual(await child.wait(), 0)
            lock = (self.runtime_dir / "flake.lock").read_bytes()
            self.write_flake('export HOOK_VERSION="two"')
            second = await self.prepare()
            try:
                self.assertEqual(second.env["HOOK_VERSION"], "two")
                self.assertNotIn("HOOK_REMOVED", second.env)
                self.assertEqual(lock, (self.runtime_dir / "flake.lock").read_bytes())
            finally:
                second.close()
            self.assertTrue((Path(first.storage.name) / "profile").exists())
        finally:
            first.close()
        (self.runtime_dir / "flake.nix").unlink()
        plain = await self.prepare()
        self.assertEqual(plain.env, self.base)
        self.assertIsNone(plain.storage)

    async def test_restart_failure_preserves_old_process_and_success_replaces_it(self):
        launcher = self.make_launcher()
        self.assertTrue(await launcher.start_comfyui())
        old = launcher.process
        await self.wait_for_file(self.work / f"child-{old.pid}")
        for bad_config in ("invalid nix expression", None):
            if bad_config is None:
                self.write_flake("exit 7")
            else:
                (self.runtime_dir / "flake.nix").write_text(bad_config)
            await launcher.restart_comfyui()
            self.assertIs(launcher.process, old)
            self.assertIsNone(old.poll())
            self.assertIn("reload failed", launcher.status_text)
        self.write_flake('export HOOK_VERSION="two"')
        await launcher.restart_comfyui()
        self.assertIsNot(launcher.process, old)
        self.assertIsNotNone(old.poll())
        child_file = self.work / f"child-{launcher.process.pid}"
        await self.wait_for_file(child_file)
        self.assertEqual(child_file.read_text(), "two")

    async def test_quit_cancels_hook_and_does_not_start_server(self):
        launcher = self.make_launcher()
        self.write_flake('echo $$ > "$WORK_DIR/hook-pid"; sleep 120')
        start = asyncio.create_task(launcher.start_comfyui())
        await self.wait_for_file(self.work / "hook-pid")
        pid = int((self.work / "hook-pid").read_text())
        await asyncio.wait_for(launcher.shutdown(), 10)
        self.assertFalse(await start)
        self.assertIsNone(launcher.process)
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
