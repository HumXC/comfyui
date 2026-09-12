# ComfyUI runtime environment

`comfyui-setup` creates an example only. The extra environment is disabled by default; no Git repository or top-level symlink is needed:

```text
~/.config/comfyui/
├── runtime/
│   ├── flake.nix.example  # created by setup; includes activation instructions
│   ├── flake.nix          # created by the user to enable the environment
│   └── flake.lock         # created by Nix on first resolution
├── ComfyUI/
└── .venv/
```

To enable it, copy `~/.config/comfyui/runtime/flake.nix.example` to `~/.config/comfyui/runtime/flake.nix`, edit the latter, then use the tray's **Restart**. To disable it, move `runtime/flake.nix` out of the way and restart. Editing or moving files does not affect an already running task.

The launcher checks only `runtime/flake.nix`. When absent, it uses the built-in environment without invoking Nix. The example and any old top-level `flake.nix` are ignored. An invalid runtime flake or broken runtime flake symlink produces an error rather than silently disabling the environment.

Only `runtime/` becomes the flake source; the checkout, models and virtual environment are outside it. You can add Nix files inside `runtime/` and import them with relative paths. Keep large data and secrets outside that directory: Nix copies flake sources into its store.

Setup creates `flake.nix.example` only when absent. It preserves both edited examples and active configuration, and does not re-enable a disabled environment.

Use the tray's **Open Runtime Environment** entry to open the active flake, or the example when disabled. If neither exists, run `comfyui-setup` first.

## Adding native dependencies

The generated template uses `devShells.<system>.default` and the same nixpkgs revision as the packaged launcher. Add libraries needed by custom nodes to `runtimeLibraries`, for example:

```nix
runtimeLibraries = [
  pkgs.libxcb
  pkgs.gtk3
];
```

The template exposes these packages and sets `LD_LIBRARY_PATH` with `lib.makeLibraryPath`. Putting a package in `packages` alone does not guarantee that a Python wheel can locate its shared libraries. GTK introspection, schemas and plugins may need additional variables depending on the node; declare those in the devShell or its hook.

## shellHook and restarts

When `runtime/flake.nix` exists, each start/restart runs `nix develop` asynchronously and executes `shellHook`. Its exported variables are collected for the new ComfyUI process. The hook's output and Nix errors go to the launcher's stdout/stderr. For example:

```nix
shellHook = ''
  export MY_NODE_SETTING="enabled"
  test -d "$WORK_DIR/ComfyUI" || exit 1
'';
```

Use `exit 1` (or explicitly enable shell error handling) when a failing check must abort preparation. Hooks follow Nix shell semantics: a command returning nonzero does not automatically terminate the shell. Do not launch persistent background services from the hook. Preparation happens while the old ComfyUI is still running, so avoid modifying files it is actively using.

The launcher waits for preparation, including the hook, to finish before stopping the old ComfyUI. If preparation fails, the old process remains running and the tray reports the failure. On initial failure the tray remains available for another attempt. Once preparation succeeds, the old process is stopped and the new one starts; a later Python/application startup failure cannot restore the old process.

The collected environment is rebuilt from the launcher's original environment every time. Removing a variable from the flake removes it on the next restart, unless it was also present in that original environment. The launcher retains its built-in native libraries, puts `.venv/bin` first in `PATH`, and sets `VIRTUAL_ENV` to the existing venv. ComfyUI always starts in its repository directory. Temporary build-directory variables from Nix are restored to the launcher's values because that directory is removed when preparation finishes. Shell aliases, non-exported variables, working-directory changes and shell process state such as `ulimit` are not transferred to Python.

The prepared Nix profile is retained as a GC root while its environment is used. Restarting never runs `nix flake update`; unchanged inputs keep their locked versions. Nix may update the lock if you change input declarations. To deliberately update all inputs, run:

```sh
nix flake update --flake ~/.config/comfyui/runtime
```

This applies to tray starts/restarts. A custom node or ComfyUI Manager that restarts Python internally can inherit the current environment; use the tray to reload Nix configuration. Setup and update keep using their existing dependency-installation environment.
