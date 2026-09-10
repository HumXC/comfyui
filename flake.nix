{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/cbe2b76406d5567bfc9a9a6eca0320885bc108c4";

  outputs = {nixpkgs, ...}: let
    forAllSystems = nixpkgs.lib.genAttrs [
      "aarch64-linux"
      "x86_64-linux"
    ];
  in {
    devShells = import ./nix/shells.nix {inherit nixpkgs forAllSystems;};
    packages = import ./nix/packages.nix {inherit nixpkgs forAllSystems;};
  };
}
