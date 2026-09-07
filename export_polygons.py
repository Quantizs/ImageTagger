"""Export annotated copies: python export_polygons.py IMAGE_DIRECTORY [-o OUTPUT]."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image

from annotation_store import IMAGE_EXTENSIONS, atomic_write, parse_annotations
from export_layout import compose_export as draw_polygons, line_width

MANIFEST = ".polygon_export.json"


def save_png(image: Image.Image, destination: Path) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".export-", delete=False) as handle:
            temporary = Path(handle.name)
            image.save(handle, format="PNG")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_images(directory: Path, output: Path | None = None, ratio: float = 0.003, crop_height: int = 320) -> dict:
    directory = Path(directory).expanduser().resolve()
    output = (Path(output).expanduser() if output is not None else directory / "output").resolve()
    if not directory.is_dir():
        raise ValueError("A képmappa nem létezik.")
    if not math.isfinite(ratio) or not 0 < ratio <= 0.1:
        raise ValueError("A vonalarány 0-nál nagyobb és legfeljebb 0.1 lehet.")
    if not isinstance(crop_height, int) or not 120 <= crop_height <= 1600:
        raise ValueError("A kivágások magassága 120 és 1600 pixel közötti egész szám legyen.")
    annotations = directory / "annotations"
    if not annotations.is_dir():
        raise ValueError(f"Nem található annotációs mappa: {annotations}")
    if output == directory or output in directory.parents or output == annotations.resolve() or annotations.resolve() in output.parents:
        raise ValueError("Az output külön mappa legyen; nem lehet a képmappa, annak szülője vagy az annotations mappa része.")

    previous = set()
    manifest_path = output / MANIFEST
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("source") != str(directory):
            raise ValueError("Ez az output mappa másik exporthoz tartozik; válassz másik mappát.")
        filenames = manifest.get("files")
        if not isinstance(filenames, list) or any(
            not isinstance(name, str) or Path(name).name != name or not name.endswith(".png")
            or "/" in name or "\\" in name or ":" in name for name in filenames
        ):
            raise ValueError("Hibás exportnyilvántartás; válassz másik output mappát.")
        previous = set(filenames)
    if output.exists():
        unknown = [path.name for path in output.iterdir() if path.name not in previous | {MANIFEST}]
        if unknown:
            raise ValueError("Az output mappa más fájlokat is tartalmaz. Válassz üres vagy korábban ezzel a scripttel létrehozott mappát.")
    output.mkdir(parents=True, exist_ok=True)
    # Keep an ownership record even if the process is interrupted during export.
    def remember(names):
        atomic_write(manifest_path, json.dumps({"source": str(directory), "files": sorted(names)},
                                              ensure_ascii=False, indent=2) + "\n")

    remember(previous)
    exported = set()
    report = {"exported_images": 0, "polygons": 0, "skipped_images": 0, "errors": [], "output": str(output)}
    for path in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        annotation = annotations / (path.name + ".txt")
        try:
            if not annotation.exists():
                report["skipped_images"] += 1
                continue
            polygons = parse_annotations(annotation.read_text(encoding="utf-8-sig"))
            if not polygons:
                report["skipped_images"] += 1
                continue
            # Full source filename prevents collisions between e.g. photo.jpg and photo.png.
            name = path.name + ".png"
            with Image.open(path) as source:
                with draw_polygons(source, polygons, ratio, crop_height, title=path.name) as rendered:
                    remember(previous | exported | {name})
                    save_png(rendered, output / name)
            exported.add(name)
            report["exported_images"] += 1
            report["polygons"] += len(polygons)
        except (OSError, ValueError, Image.DecompressionBombError) as exc:
            report["errors"].append(f"{path.name}: {exc}")
    # Remove only this script's previous exports when their annotations were deleted.
    for name in previous - exported:
        (output / name).unlink(missing_ok=True)
    remember(exported)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Háromszínű poligonkeretek, sorszámok és perspektívajavított táblák oldalsávon.")
    parser.add_argument("directory", type=Path, help="Az annotált képeket tartalmazó munkamappa")
    parser.add_argument("-o", "--output", type=Path, help="Kimeneti mappa (alapértelmezés: képmappa/output)")
    parser.add_argument("--line-ratio", type=float, default=0.003,
                        help="Egy színsáv vastagsága a rövidebb képoldal arányában (alapérték: 0.003)")
    parser.add_argument("--crop-height", type=int, default=320,
                        help="Az oldalsáv kivágásainak egységes magassága pixelben (120–1600; alapérték: 320)")
    args = parser.parse_args()
    try:
        report = export_images(args.directory, args.output, args.line_ratio, args.crop_height)
    except (OSError, ValueError) as exc:
        print(f"Hiba: {exc}", file=sys.stderr)
        return 1
    print(f"Exportált kép: {report['exported_images']} | Poligon: {report['polygons']} | "
          f"Annotáció nélkül kihagyva: {report['skipped_images']} | Hibás: {len(report['errors'])}")
    print(f"Kimenet: {report['output']}")
    for error in report["errors"]:
        print(f"Hiba: {error}", file=sys.stderr)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
