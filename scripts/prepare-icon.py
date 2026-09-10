#!/usr/bin/env python3

import io
import sys
import urllib.request
from pathlib import Path

from PIL import Image

ICON_URL = "https://framerusercontent.com/images/VYwSRlkOR01d0rBJ6hcCnzXNBc.png"

ROOT_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT_DIR / "assets"

PNG_PATH = ASSETS_DIR / "comfyui.png"
ARGB_PATH = ASSETS_DIR / "comfyui.argb"

TRAY_SIZE = 64


def download_icon(url: str) -> bytes:
    print(f"Downloading: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
        },
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def rgba_to_argb(image: Image.Image) -> bytes:
    """
    Convert Pillow RGBA pixels into StatusNotifierItem ARGB32
    network-byte-order representation:

        RGBA: R G B A
        SNI:  A R G B
    """
    rgba = image.convert("RGBA")

    output = bytearray(rgba.width * rgba.height * 4)

    src = rgba.tobytes()

    for i in range(0, len(src), 4):
        r = src[i]
        g = src[i + 1]
        b = src[i + 2]
        a = src[i + 3]

        output[i] = a
        output[i + 1] = r
        output[i + 2] = g
        output[i + 3] = b

    return bytes(output)


def main() -> int:
    ASSETS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    data = download_icon(ICON_URL)

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception as exc:
        print(
            f"Invalid image: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"Source image: {image.width}x{image.height} " f"{image.mode}")

    # ------------------------------------------------------------
    # Desktop / icon theme PNG
    # ------------------------------------------------------------

    theme_icon = image.convert("RGBA")

    theme_icon.save(
        PNG_PATH,
        format="PNG",
        optimize=True,
    )

    print(f"PNG:  {PNG_PATH}")

    # ------------------------------------------------------------
    # Tray ARGB32
    # ------------------------------------------------------------

    tray_icon = image.convert("RGBA")

    tray_icon.thumbnail(
        (TRAY_SIZE, TRAY_SIZE),
        Image.Resampling.LANCZOS,
    )

    # Keep the tray pixmap exactly 64x64 without stretching the image.
    canvas = Image.new(
        "RGBA",
        (TRAY_SIZE, TRAY_SIZE),
        (0, 0, 0, 0),
    )

    x = (TRAY_SIZE - tray_icon.width) // 2
    y = (TRAY_SIZE - tray_icon.height) // 2

    canvas.alpha_composite(
        tray_icon,
        (x, y),
    )

    argb = rgba_to_argb(canvas)

    ARGB_PATH.write_bytes(argb)

    expected_size = TRAY_SIZE * TRAY_SIZE * 4

    assert len(argb) == expected_size

    print(f"ARGB: {ARGB_PATH} " f"({len(argb)} bytes, " f"{TRAY_SIZE}x{TRAY_SIZE})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
