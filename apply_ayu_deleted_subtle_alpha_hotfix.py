#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_DELETED_TELEGRAM_NEUTRAL_BUBBLE_v0_3"


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
        print("[ayu-deleted-telegram-theme] already installed")
        return 0

    # For the Telegram-theme option, do not bake alpha into the image. We want the
    # exact static theme bubble artwork and then one final 0.5 layer-alpha operation.
    # Custom Ayu colors keep their existing cached image-alpha path.
    old_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? ayuDeletedAlpha : nil\n"
    new_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible && !ayuTelegramThemeDeleted ? ayuDeletedAlpha : nil\n"
    text = one(text, old_image_alpha, new_image_alpha, "Telegram-theme image alpha bypass")

    # Night/wallpaper themes can render their bubble through WallpaperBubbleBackgroundNode.
    # That backdrop inherits the wallpaper tint (purple in the built-in Night theme), so
    # making it transparent only exposes even more of the colored wallpaper. For a deleted
    # message using 'Telegram theme', force Telegram's normal static theme bubble image
    # instead. This preserves the theme's own neutral incoming/outgoing bubble color.
    old_mask = "        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n"
    new_mask = '''        // AYU_DELETED_TELEGRAM_NEUTRAL_BUBBLE_v0_3\n        let ayuBackgroundMaskMode = ayuTelegramThemeDeleted ? false : (ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false)\n'''
    text = one(text, old_mask, new_mask, "Telegram-theme static bubble source")

    old_block = '''        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3\n        // If Telegram produced a normal bubble image, its alpha is already baked and\n        // cached by ChatMessageBackground. If the image is nil, the theme is using\n        // the wallpaper/backdrop bubble path; fade that one layer instead. Never hide\n        // both layers, and never change text/media/status opacity.\n        if ayuTelegramThemeDeleted && !strongSelf.backgroundNode.hasImage {\n            strongSelf.backgroundWallpaperNode.alpha = ayuDeletedAlpha\n        } else if ayuDeletedVisible && ayuDeletedBackgroundColor != nil {\n            strongSelf.backgroundWallpaperNode.alpha = 0.0\n        } else {\n            strongSelf.backgroundWallpaperNode.alpha = 1.0\n        }\n'''
    new_block = '''        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3\n        // For Telegram-theme deleted messages the mask mode above is deliberately\n        // disabled, so backgroundNode contains Telegram's static theme bubble instead\n        // of the wallpaper-tinted backdrop. Apply the requested deleted alpha once.\n        if ayuTelegramThemeDeleted {\n            strongSelf.backgroundNode.alpha = ayuDeletedAlpha\n            strongSelf.backgroundWallpaperNode.alpha = 0.0\n        } else if ayuDeletedVisible && ayuDeletedBackgroundColor != nil {\n            strongSelf.backgroundNode.alpha = 1.0\n            strongSelf.backgroundWallpaperNode.alpha = 0.0\n        } else {\n            strongSelf.backgroundNode.alpha = 1.0\n            strongSelf.backgroundWallpaperNode.alpha = 1.0\n        }\n'''
    text = one(text, old_block, new_block, "Telegram-theme neutral bubble rendering")

    path.write_text(text, encoding="utf-8")
    print("[ayu-deleted-telegram-theme] Night/wallpaper tint bypassed; stock theme bubble at configured alpha")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
