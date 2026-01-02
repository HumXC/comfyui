{
  nixpkgs,
  forAllSystems,
  kernel-builder,
}:
forAllSystems (
  system: let
    pkgs = nixpkgs.legacyPackages.${system};
    python = pkgs.python3;
    pythonPackages = pkgs.python3Packages;
    lib = import ./lib.nix {inherit kernel-builder;};
  in
    with pkgs; {
      default = mkShell {
        packages = [
          python
          pythonPackages.venvShellHook
        ];

        venvDir = "./.venv";
        # 设置 LD_LIBRARY_PATH 以便 Python 包能找到系统库和 Intel GPU 驱动
        LD_LIBRARY_PATH = lib.mkLibraryPath pkgs;
        ONEAPI_DEVICE_SELECTOR = "level_zero:gpu";
        ZES_ENABLE_SYSMAN = 1;
        NEOReadDebugKeys = 1;
        OverrideDefaultFP64Settings = 1;
      };
    }
)
