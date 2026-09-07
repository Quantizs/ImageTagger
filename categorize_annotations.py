"""Assign aspect-based categories to existing labels, preserving manual choices."""

import argparse
import sys
from pathlib import Path

from annotation_store import AnnotationStore


def categorize_directory(directory: Path, dry_run=False) -> dict:
    store = AnnotationStore(directory)
    report = {"changed": 0, "manual_preserved": 0, "unchanged": 0, "changed_images": 0, "errors": []}
    for record in store.records:
        try:
            counts = store.categorize_record(record, dry_run)
            if not dry_run:
                store.save_record(record)
            for key in ("changed", "manual_preserved", "unchanged"):
                report[key] += counts[key]
            report["changed_images"] += bool(counts["changed"])
        except (OSError, ValueError) as exc:
            # Do not retry failed records implicitly when saving statistics.
            record.dirty = False
            report["errors"].append(f"{record.path.name}: {exc}")
    if not dry_run:
        # Reload to calculate statistics from what actually reached disk.
        AnnotationStore(directory).save_statistics()
    return report


def main():
    parser = argparse.ArgumentParser(description="Régi és automatikus annotációk kategorizálása. A kézi kategóriák megmaradnak.")
    parser.add_argument("directory", type=Path, help="A képeket és az annotations mappát tartalmazó munkamappa")
    parser.add_argument("--dry-run", action="store_true", help="Csak összesítés, fájlmódosítás nélkül")
    args = parser.parse_args()
    try:
        report = categorize_directory(args.directory, args.dry_run)
    except (OSError, ValueError) as exc:
        print(f"Hiba: {exc}", file=sys.stderr)
        return 1
    print("Előnézet, mentés nélkül:" if args.dry_run else "Kategorizálás kész:")
    print(f"Módosuló objektum: {report['changed']} | Érintett kép: {report['changed_images']} | "
          f"Megőrzött kézi: {report['manual_preserved']} | Változatlan automatikus: {report['unchanged']}")
    for error in report["errors"]:
        print(f"Hiba: {error}", file=sys.stderr)
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
