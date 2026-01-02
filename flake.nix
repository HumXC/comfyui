{
  # inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  # 为了使用 24 版本的 intel-compute-runtime
  # https://www.nixhub.io/packages/intel-compute-runtime
  inputs.nixpkgs.url = "nixpkgs/44e422ba8ed1bdec9620b0733601669972f91170";
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
