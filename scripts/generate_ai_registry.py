from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ai_registry.scaffold import generate_registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", default="apis")
    parser.add_argument("--output-dir", default="ai_registry")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        generate_registry(Path(args.input_dir), Path(args.output_dir))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
