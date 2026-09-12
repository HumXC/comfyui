# 可选运行环境：setup 只生成此示例，默认不启用，也不运行 nix develop。
# 启用：在 ~/.config/comfyui/runtime/ 中将 flake.nix.example 复制为 flake.nix，
# 按需编辑，然后通过托盘 Restart 应用。无需顶层链接或 Git 仓库。
# 禁用：移走 runtime/flake.nix，然后通过托盘 Restart 恢复内置环境。
# setup 不覆盖已有示例或 flake.nix，也不会重新启用已禁用的环境。
#
# 存在 runtime/flake.nix 时，每次启动/托盘重启都加载 default devShell，
# 执行 shellHook 并传递 export 的变量；仅编辑本文件不会影响正在运行的任务。
# 新环境准备成功后才停止旧 ComfyUI；准备失败保留旧进程并报告错误。
# shellHook 的必要检查请使用 `exit 1` 中止；不要在 hook 中启动后台服务。
# 别名、cd、ulimit 等 shell 进程状态不会传递给 Python。
# 内置 GPU 库保留，.venv/bin 优先，ComfyUI 仍在其源码目录运行。
#
# 可在 runtime/ 内 import ./其他文件.nix。整个 runtime/ 会进入 Nix store，
# 请勿在此目录存放模型、大文件或秘密。首次加载会生成 flake.lock；
# 重启不主动更新锁定版本，修改 inputs 时 Nix 可能更新 lock。
# 节点内部重启不保证重载环境；修改配置后请使用托盘 Restart。
{
  inputs.nixpkgs.url = "@nixpkgsUrl@";

  outputs = {nixpkgs, ...}: let
    forAllSystems = nixpkgs.lib.genAttrs ["x86_64-linux" "aarch64-linux"];
  in {
    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      runtimeLibraries = [
        # Uncomment the libraries your custom nodes need.
        # pkgs.libxcb
        # pkgs.gtk3
      ];
    in {
      default = pkgs.mkShell {
        packages = runtimeLibraries;
        # Python wheels need a dynamic library search path as well as packages.
        LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath runtimeLibraries;
        shellHook = ''
          # Export variables here; this runs on every tray start/restart.
          # export MY_NODE_SETTING="value"
          # Use `exit 1` to abort preparation on a required check failure.
        '';
      };
    });
  };
}
