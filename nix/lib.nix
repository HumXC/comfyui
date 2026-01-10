{kernel-builder}: {
  mkLibraryPath = pkgs:
    with pkgs;
      lib.makeLibraryPath [
        stdenv.cc.cc.lib
        level-zero
        intel-compute-runtime
        libGL
        libGLU
        glib

        # Level Zero GPU runtime from kernel-builder.
        (callPackage
          "${kernel-builder}/pkgs/xpu-packages/ocloc.nix"
          {
            ocloc = null;
          })
      ];
}
