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
    preview_source = Path(__file__).resolve().parent / "payload/AyuGramAppIconPreview.png"
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

    # Register the same artwork in Telegram's stock icon picker. It is the
    # primary icon (nil alternate-icon name), so it must be the first and only
    # default entry rather than a fake alternate icon.
    preview_target = root / "Telegram/Telegram-iOS/Icons.xcassets/AyuGramIcon.imageset"
    preview_target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(preview_source, preview_target / "AyuGramIcon.png")
    preview_contents = {
        "images": [
            {"filename": "AyuGramIcon.png", "idiom": "universal", "scale": "1x"},
            {"idiom": "universal", "scale": "2x"},
            {"idiom": "universal", "scale": "3x"},
        ],
        "info": {"author": "xcode", "version": 1},
    }
    (preview_target / "Contents.json").write_text(json.dumps(preview_contents, indent=2) + "\n", encoding="utf-8")

    app_delegate = root / "submodules/TelegramUI/Sources/AppDelegate.swift"
    app_text = app_delegate.read_text(encoding="utf-8")
    marker = "AYU_APP_ICON_PICKER_v2"
    if marker not in app_text:
        anchor = '                    PresentationAppIcon(name: "BlueIcon", imageName: "BlueIcon", isDefault: buildConfig.isAppStoreBuild),\n'
        if app_text.count(anchor) != 1:
            raise RuntimeError(f"app icon picker anchor: expected 1, found {app_text.count(anchor)}")
        app_text = app_text.replace(
            anchor,
            '                    // AYU_APP_ICON_PICKER_v2\n'
            '                    PresentationAppIcon(name: "AyuGram", imageName: "AyuGramIcon", isDefault: true),\n'
            '                    PresentationAppIcon(name: "BlueIcon", imageName: "BlueIcon"),\n',
            1,
        )
        app_delegate.write_text(app_text, encoding="utf-8")

    if not (target / "AyuGramAppIcon.png").is_file():
        raise RuntimeError("AyuGram app icon missing")
    if "AyuGramAppIcon.png" not in (target / "Contents.json").read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram app icon catalog incomplete")
    if 'PresentationAppIcon(name: "AyuGram", imageName: "AyuGramIcon", isDefault: true)' not in app_delegate.read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram default picker entry missing")
    print("[ayu-app-icon] AyuGram artwork is the primary icon and first stock-picker default")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
