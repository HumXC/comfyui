{nixpkgs}: {
  forAllSystems = nixpkgs.lib.genAttrs [
    "aarch64-linux"
    "x86_64-linux"
  ];

  mkLibraryPath = pkgs:
    pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.level-zero
    ];
}
