{
  nixpkgs,
  forAllSystems,
}:
forAllSystems (
  system: let
    pkgs = nixpkgs.legacyPackages.${system};
    python = pkgs.python3;
    lib = import ./lib.nix { inherit nixpkgs; };
    # 提取库路径
    libPath = lib.mkLibraryPath pkgs;

    pythonBin = "${python}/bin/python3";
    runSrc = ../scripts/comfyui-run.py;
    updateSrc = ../scripts/comfyui-update.py;
    stopSrc = ../scripts/comfyui-stop.py;

    mkPythonScript = name: src:
      pkgs.runCommand name {} ''
        mkdir -p $out/bin
        cp ${src} $out/bin/${name}
        substituteInPlace $out/bin/${name} \
          --replace "__PYTHON_BIN__" "${pythonBin}" \
          --replace "__LIB_PATH__" "${libPath}" \
          --replace "#!/usr/bin/env python3" "#!${pythonBin}"
        chmod +x $out/bin/${name}
      '';

    # 从网络获取图标
    iconUrl = "https://framerusercontent.com/images/VYwSRlkOR01d0rBJ6hcCnzXNBc.png";
    icon = pkgs.fetchurl {
      url = iconUrl;
      sha256 = "sha256-p8v3SMaJGHmbttIpjZQFy32qHuDZFHYwlWazjMTuJoY="; # 首次运行时会显示正确的 hash
    };

desktopItem = pkgs.makeDesktopItem {
  name = "comfyui";
  desktopName = "ComfyUI";
  comment = "ComfyUI Application";
  icon = "comfyui";
  exec = "comfyui-run";
  categories = ["Development"];

  # 直接定义 actions 结构体
  actions = {
    "Run" = {
      name = "Run ComfyUI";
      exec = "comfyui-run";
    };
    "Stop" = {
      name = "Stop ComfyUI";
      exec = "comfyui-stop";
    };
    "Update" = {
      name = "Update ComfyUI";
      exec = "comfyui-update";
    };
  };
};
  in rec {
    run = mkPythonScript "comfyui-run" runSrc;
    update = mkPythonScript "comfyui-update" updateSrc;
    stop = mkPythonScript "comfyui-stop" stopSrc;

    default = pkgs.stdenv.mkDerivation {
      name = "comfyui-full";
      src = runSrc;
      dontUnpack = true;
      installPhase = ''
        mkdir -p $out/bin
        cp -r ${run}/bin/* $out/bin/
        cp -r ${update}/bin/* $out/bin/
        cp -r ${stop}/bin/* $out/bin/

        mkdir -p $out/share/applications
        cp -r ${desktopItem}/share/applications/* $out/share/applications/

        mkdir -p $out/share/icons/hicolor/512x512/apps
        cp ${icon} $out/share/icons/hicolor/512x512/apps/comfyui.png
      '';
    };
  }
)
