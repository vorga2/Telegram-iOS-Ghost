#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from apply_ayu_branding_hotfix import main as apply_branding_main

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
    if MARK not in text:
        obsolete_flag = "        let ayuTelegramThemeDeleted = ayuDeletedVisible && ayuDeletedBackgroundColor == nil\n"
        text = one(text, obsolete_flag, "", "obsolete Telegram-theme deleted flag")

        old_image_alpha = "        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? ayuDeletedAlpha : nil\n"
        text = one(text, old_image_alpha, "        strongSelf.backgroundNode.ayuCustomImageAlpha = nil\n", "disable baked deleted alpha")

        mask_anchor = "        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n"
        text = one(text, mask_anchor, f"        // {MARK}\n" + mask_anchor, "stock Telegram background mode")

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
    else:
        print("[ayu-deleted-alpha] already installed")

    # Keep Telegram's theme calculation stock, but explicitly bridge the resulting
    # PresentationTheme to UIKit's native Liquid Glass subtree. This is required on
    # iOS 26/27 because Telegram can change its custom theme without changing the
    # system appearance that UIGlassEffect would otherwise inherit.
    native_sync = Path(__file__).resolve().with_name("apply_ayu_native_appearance_sync.py")
    if not native_sync.exists():
        raise RuntimeError(f"missing native appearance sync patch: {native_sync}")
    subprocess.run([sys.executable, str(native_sync), str(root)], check=True)

    # Build-time branding + CallKit provider display name.
    saved_argv = sys.argv
    try:
        sys.argv = [str(Path(__file__).with_name("apply_ayu_branding_hotfix.py")), str(root)]
        result = apply_branding_main()
    finally:
        sys.argv = saved_argv
    if result != 0:
        raise RuntimeError(f"AyuGram branding patch failed with code {result}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
