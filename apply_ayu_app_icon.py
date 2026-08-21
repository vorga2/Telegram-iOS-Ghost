#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_app_icon.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    source = Path(__file__).resolve().parent / "payload/AyuGramAppIcon.png"
    target = root / "Telegram/Telegram-iOS/DefaultAppIcon.xcassets/AppIconLLC.appiconset"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target / "AyuGramAppIcon.png")
    contents = {
        "images": [
            {
                "filename": "AyuGramAppIcon.png",
                "idiom": "universal",
                "platform": "ios",
                "size": "1024x1024",
            }
        ],
        "info": {
            "author": "xcode",
            "version": 1,
        },
    }
    (target / "Contents.json").write_text(json.dumps(contents, indent=2) + "\n", encoding="utf-8")

    if not (target / "AyuGramAppIcon.png").is_file():
        raise RuntimeError("AyuGram app icon missing")
    if "AyuGramAppIcon.png" not in (target / "Contents.json").read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram app icon catalog incomplete")
    print("[ayu-app-icon] supplied AyuGram artwork installed as the default iOS app icon")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
