#!/usr/bin/env python3
"""Extract and decompile TellStick Net v2 / ZNet firmware modules.

The image is an OpenWrt SquashFS rootfs holding Python 2.7 ``.pyc`` files.  Only
the requested module roots are decompiled — turning the whole rootfs into source
is neither useful nor something we can commit.

Usage:
    python3 tools/decompile_znet_firmware.py
    python3 tools/decompile_znet_firmware.py --modules productiontest,rf433,telldus
    python3 tools/decompile_znet_firmware.py --out /tmp/znet-decompile

Requirements (verified with the versions in brackets):
    pip install PySquashfsImage uncompyle6        # 0.9.0, 3.9.3

The output directory is git-ignored: it contains Telldus' vendor source.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

DEFAULT_IMAGE = "tellstick-znet-lite-v2-1.3.2.bin"
DEFAULT_MODULES = "productiontest,rf433,telldus"
SITE_PACKAGES = "usr/lib/python2.7/site-packages/"


def find_squashfs_offset(blob: bytes) -> int:
    """Return the offset of the SquashFS superblock ('hsqs')."""
    offset = blob.find(b"hsqs")
    if offset < 0:
        raise SystemExit("No SquashFS superblock found in the image")
    return offset


def extract(image: pathlib.Path, modules: list[str], pyc_dir: pathlib.Path) -> int:
    """Write the matching .pyc files from the image into ``pyc_dir``."""
    from PySquashfsImage import SquashFsImage  # noqa: PLC0415

    offset = find_squashfs_offset(image.read_bytes())
    img = SquashFsImage.from_file(str(image), offset)
    count = 0
    for entry in img:
        path = getattr(entry, "path", None)
        if not path:
            continue
        rel = str(path).lstrip("/")
        if not rel.endswith(".pyc") or SITE_PACKAGES not in rel:
            continue
        module = rel.split(SITE_PACKAGES, 1)[1]
        if not any(module.startswith(f"{m}/") for m in modules):
            continue
        dest = pyc_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(entry.read_bytes())
        count += 1
    return count


def _uncompyle6_command() -> list[str]:
    """Find uncompyle6: venv sibling of the interpreter first, then PATH."""
    local = pathlib.Path(sys.executable).with_name("uncompyle6")
    if local.is_file():
        return [str(local)]
    found = shutil.which("uncompyle6")
    if found:
        return [found]
    raise SystemExit("uncompyle6 not installed (pip install uncompyle6)")


def decompile(pyc_dir: pathlib.Path, src_dir: pathlib.Path) -> tuple[int, list[str]]:
    """Decompile every extracted .pyc; return (successes, failure summaries)."""
    tool = _uncompyle6_command()
    src_dir.mkdir(parents=True, exist_ok=True)
    ok, failed = 0, []
    for pyc in sorted(pyc_dir.rglob("*.pyc")):
        res = subprocess.run(  # noqa: S603
            [*tool, "-o", str(src_dir), str(pyc)], capture_output=True, text=True
        )
        if res.returncode == 0:
            ok += 1
        else:
            last = (res.stderr or res.stdout or "").strip().splitlines()[-1:]
            failed.append(f"{pyc.name}: {' '.join(last)}")
    return ok, failed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", default=DEFAULT_IMAGE, help="firmware image")
    parser.add_argument("--modules", default=DEFAULT_MODULES, help="comma-separated roots")
    parser.add_argument("--out", default="znet-decompile", help="output directory")
    args = parser.parse_args()

    image = pathlib.Path(args.image)
    if not image.is_file():
        raise SystemExit(f"Firmware image not found: {image}")

    out = pathlib.Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    pyc_dir, src_dir = out / "pyc", out / "src"
    modules = [m.strip() for m in args.modules.split(",") if m.strip()]

    extracted = extract(image, modules, pyc_dir)
    print(f"extracted {extracted} .pyc from {image.name} (modules: {', '.join(modules)})")
    ok, failed = decompile(pyc_dir, src_dir)
    print(f"decompiled {ok} file(s) into {src_dir}")
    for line in failed[:10]:
        print(f"  failed: {line}")
    print("Output is Telldus' Python 2.7 source — do not commit it.")
    return 0 if extracted else 1


if __name__ == "__main__":
    raise SystemExit(main())
