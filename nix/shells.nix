{
  nixpkgs,
  forAllSystems,
}:
forAllSystems (
  system: let
    pkgs = nixpkgs.legacyPackages.${system};
    python = pkgs.python3.withPackages (ps: [
      ps.pillow
    ]);
    libPath = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.level-zero
      pkgs.intel-compute-runtime
      pkgs.intel-graphics-compiler

      pkgs.libGL
      pkgs.libGLU
      pkgs.glib
    ];
  in
    with pkgs; {
      default = mkShell {
        packages = [
          python
          intel-compute-runtime
          intel-graphics-compiler
        ];

        # 设置 LD_LIBRARY_PATH 以便 Python 包能找到系统库和 Intel GPU 驱动
        LD_LIBRARY_PATH = libPath;
        ONEAPI_DEVICE_SELECTOR = "level_zero:gpu";
        ZES_ENABLE_SYSMAN = 1;
        NEOReadDebugKeys = 1;
        IGC_EnableDPEmulation = 1;
        OverrideDefaultFP64Settings = 1;
        OCL_ICD_VENDORS = "${pkgs.intel-compute-runtime}/etc/OpenCL/vendors";
        ZEBIN_PATH = "${pkgs.intel-graphics-compiler}/bin";
      };
    }
)
