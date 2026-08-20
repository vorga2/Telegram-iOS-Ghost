#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_DELETED_NORMAL_STOCK_ALPHA_v0_3"


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
        print("[ayu-deleted-alpha] already installed")
        return 0

    # Do not synthesize a different bubble image for deleted messages. Telegram
    # has already selected the correct light/dark/chat-theme artwork at this point.
    # We only change the final opacity of the active bubble layer.
    old_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? ayuDeletedAlpha : nil\n"
    new_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = nil\n"
    text = one(text, old_image_alpha, new_image_alpha, "disable baked deleted alpha")

    # Keep Telegram's own mask/backdrop decision untouched. In particular, do not
    # force wallpaper-backed themes into the static-image path.
    mask_anchor = "        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n"
    mask_replacement = f"        // {MARK}\n" + mask_anchor
    text = one(text, mask_anchor, mask_replacement, "stock Telegram background mode")

    old_block = '''        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3
        // If Telegram produced a normal bubble image, its alpha is already baked and
        // cached by ChatMessageBackground. If the image is nil, the theme is using
        // the wallpaper/backdrop bubble path; fade that one layer instead. Never hide
        // both layers, and never change text/media/status opacity.
        if ayuTelegramThemeDeleted && !strongSelf.backgroundNode.hasImage {
            strongSelf.backgroundWallpaperNode.alpha = ayuDeletedAlpha
        } else if ayuDeletedVisible && ayuDeletedBackgroundColor != nil {
            strongSelf.backgroundWallpaperNode.alpha = 0.0
        } else {
            strongSelf.backgroundWallpaperNode.alpha = 1.0
        }
'''
    new_block = '''        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3
        // Plain opacity only: preserve whatever bubble implementation Telegram chose.
        // If the normal image exists, fade it and hide the inactive wallpaper layer.
        // If Telegram chose a wallpaper-backed bubble, fade that backdrop instead.
        // Message text, media, status, reactions and the rest of the item stay at 1.0.
        if ayuDeletedVisible {
            if ayuDeletedBackgroundColor != nil {
                strongSelf.backgroundNode.alpha = ayuDeletedAlpha
                strongSelf.backgroundWallpaperNode.alpha = 0.0
            } else if strongSelf.backgroundNode.hasImage {
                strongSelf.backgroundNode.alpha = ayuDeletedAlpha
                strongSelf.backgroundWallpaperNode.alpha = 0.0
            } else {
                strongSelf.backgroundNode.alpha = ayuDeletedAlpha
                strongSelf.backgroundWallpaperNode.alpha = ayuDeletedAlpha
            }
        } else {
            strongSelf.backgroundNode.alpha = 1.0
            strongSelf.backgroundWallpaperNode.alpha = 1.0
        }
'''
    text = one(text, old_block, new_block, "normal deleted bubble opacity")

    path.write_text(text, encoding="utf-8")
    print("[ayu-deleted-alpha] stock Telegram bubble path preserved; background opacity only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
