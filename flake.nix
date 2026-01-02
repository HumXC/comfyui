{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.kernel-builder.url = "github:huggingface/kernel-builder/main";

  outputs = {
    nixpkgs,
    kernel-builder,
    ...
  }: let
    forAllSystems = nixpkgs.lib.genAttrs [
      "aarch64-linux"
      "x86_64-linux"
    ];
  in {
    devShells = import ./nix/shells.nix {inherit nixpkgs forAllSystems kernel-builder;};
    packages = import ./nix/packages.nix {inherit nixpkgs forAllSystems kernel-builder;};
  };
}
