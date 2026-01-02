{kernel-builder}: {
  mkLibraryPath = pkgs:
    pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.level-zero
      pkgs.intel-compute-runtime
      # Level Zero GPU runtime from kernel-builder.
      (pkgs.callPackage
        "${kernel-builder}/pkgs/xpu-packages/ocloc.nix"
        {
          ocloc = null;
        })
    ];
}
