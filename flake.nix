{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {nixpkgs, ...}: let
    lib = import ./nix/lib.nix {inherit nixpkgs;};
    forAllSystems = lib.forAllSystems;
  in {
    devShells = import ./nix/shells.nix {inherit nixpkgs forAllSystems;};
    packages = import ./nix/packages.nix {inherit nixpkgs forAllSystems;};
  };
}
