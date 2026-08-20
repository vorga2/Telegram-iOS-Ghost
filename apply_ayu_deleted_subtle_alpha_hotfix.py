#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_DELETED_SUBTLE_THEME_ALPHA_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_subtle_alpha_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    if not path.exists():
        raise RuntimeError(f"missing Telegram source: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print("[ayu-deleted-subtle-alpha] already installed")
        return 0

    # Telegram-theme bubbles should use layer opacity, not a pre-rendered alpha image.
    # This keeps the actual theme color/gradient and avoids visually over-dense dark
    # bubbles. Custom Ayu colors continue using the cached image-alpha path.
    old_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? ayuDeletedAlpha : nil\n"
    new_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible && !ayuTelegramThemeDeleted ? ayuDeletedAlpha : nil\n"
    text = one(text, old_image_alpha, new_image_alpha, "Telegram-theme image alpha bypass")

    old_block = '''        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3\n        // If Telegram produced a normal bubble image, its alpha is already baked and\n        // cached by ChatMessageBackground. If the image is nil, the theme is using\n        // the wallpaper/backdrop bubble path; fade that one layer instead. Never hide\n        // both layers, and never change text/media/status opacity.\n        if ayuTelegramThemeDeleted && !strongSelf.backgroundNode.hasImage {\n            strongSelf.backgroundWallpaperNode.alpha = ayuDeletedAlpha\n        } else if ayuDeletedVisible && ayuDeletedBackgroundColor != nil {\n            strongSelf.backgroundWallpaperNode.alpha = 0.0\n        } else {\n            strongSelf.backgroundWallpaperNode.alpha = 1.0\n        }\n'''
    new_block = '''        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3\n        // AYU_DELETED_SUBTLE_THEME_ALPHA_v0_3\n        // Telegram's dark bubble/backdrop is visually much denser than a flat color.\n        // Cap only the stock Telegram-theme background at 0.35. The message contents\n        // stay fully opaque. Whichever stock source Telegram actually uses gets the\n        // alpha exactly once; the inactive fill source is hidden.\n        let ayuTelegramDeletedAlpha = min(ayuDeletedAlpha, CGFloat(0.35))\n        if ayuTelegramThemeDeleted {\n            if strongSelf.backgroundNode.hasImage {\n                strongSelf.backgroundNode.alpha = ayuTelegramDeletedAlpha\n                strongSelf.backgroundWallpaperNode.alpha = 0.0\n            } else {\n                strongSelf.backgroundNode.alpha = 1.0\n                strongSelf.backgroundWallpaperNode.alpha = ayuTelegramDeletedAlpha\n            }\n        } else if ayuDeletedVisible && ayuDeletedBackgroundColor != nil {\n            strongSelf.backgroundNode.alpha = 1.0\n            strongSelf.backgroundWallpaperNode.alpha = 0.0\n        } else {\n            strongSelf.backgroundNode.alpha = 1.0\n            strongSelf.backgroundWallpaperNode.alpha = 1.0\n        }\n'''
    text = one(text, old_block, new_block, "Telegram-theme active background alpha")

    path.write_text(text, encoding="utf-8")
    print("[ayu-deleted-subtle-alpha] Telegram-theme deleted bubble capped at 0.35; active stock layer only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
