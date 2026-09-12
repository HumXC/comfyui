{
  nixpkgs,
  forAllSystems,
}:
forAllSystems (
  system: let
    torchVersion = "2.14.0+xpu";
    torchvisionVersion = "0.29.0+xpu";

    pkgs = nixpkgs.legacyPackages.${system};
    python = pkgs.python3.withPackages (ps:
      with ps; [
        dbus-next
      ]);

    # 提取库路径
    libPath = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.level-zero
      pkgs.intel-compute-runtime
      pkgs.intel-compute-runtime.drivers
      pkgs.intel-graphics-compiler
      pkgs.libGL
      pkgs.libGLU
      pkgs.glib
    ];

    pythonBin = "${python}/bin/python3";
    uvBin = "${pkgs.uv}/bin/uv";
    runSrc = ../scripts/comfyui-run.py;
    setupSrc = ../scripts/comfyui-setup.py;
    updateSrc = ../scripts/comfyui-update.py;
    runtimeTemplate = pkgs.replaceVars ../templates/runtime-flake.nix {
      nixpkgsUrl = "github:NixOS/nixpkgs/${nixpkgs.rev}";
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
        "Update" = {
          name = "Update ComfyUI";
          exec = "comfyui-update";
        };
        "Setup" = {
          name = "Setup ComfyUI";
          exec = "comfyui-setup";
        };
      };
    };
  in rec {
    setup = pkgs.runCommand "comfyui-setup" {} ''
      mkdir -p $out/bin

      cp ${setupSrc} $out/bin/comfyui-setup

      substituteInPlace $out/bin/comfyui-setup \
        --replace "#!/usr/bin/env python3" "#!${pythonBin}" \
        --replace "__TORCH_VERSION__" "${torchVersion}" \
        --replace "__TORCHVISION_VERSION__" "${torchvisionVersion}" \
        --replace "__PYTHON_BIN__" "${pythonBin}" \
        --replace "__UV_BIN__" "${uvBin}" \
        --replace "__RUNTIME_TEMPLATE__" "${runtimeTemplate}" \
        --replace "__LIB_PATH__" "${libPath}"

      chmod +x $out/bin/comfyui-setup
    '';

    run = pkgs.runCommand "comfyui-run" {} ''
      mkdir -p $out/bin

      cp ${runSrc} $out/bin/comfyui-run
      cp ${../scripts/runtime_environment.py} $out/bin/runtime_environment.py

      substituteInPlace $out/bin/comfyui-run \
        --replace "#!/usr/bin/env python3" "#!${pythonBin}" \
        --replace "__SETUP_BIN__" "${setup}/bin/comfyui-setup" \
        --replace "__NIX_BIN__" "${pkgs.nix}/bin/nix" \
        --replace "__LIB_PATH__" "${libPath}" \
        --replace "__OCL_ICD_VENDORS__" "${pkgs.intel-compute-runtime}/etc/OpenCL/vendors" \
        --replace "__ZEBIN_PATH__" "${pkgs.intel-graphics-compiler}/bin" \
        --replace "__XDG_OPEN_BIN__" "${pkgs.xdg-utils}/bin/xdg-open" \
        --replace "__ICON_ARGB_PATH__" "${../assets/comfyui.argb}"

      chmod +x $out/bin/comfyui-run
    '';

    update = pkgs.runCommand "comfyui-run" {} ''
      mkdir -p $out/bin

      cp ${updateSrc} $out/bin/comfyui-update

      substituteInPlace $out/bin/comfyui-update \
        --replace "#!/usr/bin/env python3" "#!${pythonBin}" \
        --replace "__SETUP_BIN__" "${setup}/bin/comfyui-setup" \
        --replace "__UV_BIN__" "${uvBin}" \
        --replace "__LIB_PATH__" "${libPath}"

      chmod +x $out/bin/comfyui-update
    '';

    default = pkgs.stdenv.mkDerivation {
      name = "comfyui-full";
      src = runSrc;
      dontUnpack = true;
      installPhase = ''
        mkdir -p $out/bin
        cp -r ${run}/bin/* $out/bin/
        cp -r ${update}/bin/* $out/bin/
        cp -r ${setup}/bin/* $out/bin/

        mkdir -p $out/share/applications
        cp -r ${desktopItem}/share/applications/* $out/share/applications/

        mkdir -p $out/share/icons/hicolor/512x512/apps
        cp ${../assets/comfyui.png} $out/share/icons/hicolor/512x512/apps/comfyui.png
      '';
    };
  }
)
