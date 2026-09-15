"""Строит манифест всех файлов датасета: путь, размер, контрольная сумма, число строк CSV.

Запуск: source .venv/bin/activate && python3 scripts/manifest.py > docs/data-manifest.json
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

DATASET_DIR = Path(__file__).resolve().parent.parent / "dataset"


def sha256_full(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    try:
        out = subprocess.run(["wc", "-l", str(path)], capture_output=True, text=True, check=True)
        return int(out.stdout.strip().split()[0])
    except Exception as e:
        print(f"warn: wc failed for {path}: {e}", file=sys.stderr)
        return -1


def main() -> None:
    entries = []
    for path in sorted(DATASET_DIR.iterdir()):
        if path.name.startswith("."):
            continue
        if not path.is_file():
            continue
        entry = {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_full(path),
        }
        if path.suffix == ".csv":
            entry["line_count_incl_header"] = count_lines(path)
        entries.append(entry)
        print(f"processed {path.name}", file=sys.stderr)
    print(json.dumps({"dataset_dir": str(DATASET_DIR), "files": entries}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
