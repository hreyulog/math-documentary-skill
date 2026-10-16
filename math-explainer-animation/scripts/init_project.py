#!/usr/bin/env python3
"""Create a clean local Remotion starter; never overwrite existing work."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", dest="destination", type=Path, required=True, help="New or empty project directory")
    parser.add_argument("--topic", default="马尔可夫链：预测下一步，需要记住多少过去？")
    parser.add_argument("--layout", choices=("portrait", "landscape"), default="portrait")
    args = parser.parse_args()
    destination = args.destination.expanduser().resolve()
    skill_root = Path(__file__).resolve().parents[1]
    source = skill_root / "assets" / "starter"
    if not args.topic.strip():
        parser.error("--topic must not be empty")
    if not source.is_dir():
        parser.error("Bundled assets/starter directory is missing")
    if skill_root == destination or skill_root in destination.parents:
        parser.error("Destination must not be inside the installed skill directory")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        parser.error("Destination exists and is not empty; choose a new directory")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("node_modules", "build", "output", "qa", ".cache", "__pycache__"),
    )
    config_path = destination / "src" / "config" / "series.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config.update(topic=args.topic.strip(), layout=args.layout)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {destination}")
    print("Next: pnpm install --frozen-lockfile; pnpm check; pnpm render:preview")
    print("The sample mathematics stays a card-removal example until you replace its model and scenes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
