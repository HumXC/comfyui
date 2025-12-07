{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = {nixpkgs, ...}: let
    forAllSystems = nixpkgs.lib.genAttrs [
      "aarch64-linux"
      "x86_64-linux"
    ];
  in {
    devShells = forAllSystems (
      system: let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python3.withPackages (ps:
          with ps; [
          ]);
      in
        with pkgs; {
          default = mkShell {
            package = [
              python
            ];
            shellHook = ''
              # 检查 .venv 目录是否存在,不存在则创建, 然后激活虚拟环境
              if [ ! -d .venv ]; then
                echo "Creating virtual environment..."
                ${python}/bin/python -m venv .venv
              fi
              source .venv/bin/activate
            '';
          };
        }
    );
  };
}
