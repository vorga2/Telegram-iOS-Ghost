#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_DELETED_VISUAL_COMPILE_FIX_v0_3"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_visual_compile_fix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    text = path.read_text(encoding="utf-8")

    if MARK in text:
        print(f"[ayu-deleted-visual-compile-fix] already patched: {path}")
        return 0

    old_decl = "        let ayuDeletedBackgroundColor: UIColor?\n        let ayuUsesTelegramTheme: Bool\n"
    if old_decl not in text:
        raise RuntimeError("deleted visual compile fix: ayuUsesTelegramTheme declaration not found")

    text = text.replace(
        old_decl,
        "        // AYU_DELETED_VISUAL_COMPILE_FIX_v0_3: removed dead ayuUsesTelegramTheme flag\n        let ayuDeletedBackgroundColor: UIColor?\n",
        1,
    )

    # Whole-message opacity is handled by ChatMessageItemImpl now. The old
    # per-bubble Telegram-theme flag became write-only after that migration and
    # Swift's warnings-as-errors correctly rejects it. Keep the .telegram branch
    # by selecting the stock bubble (nil custom fill), but remove the dead flag.
    for line in (
        "                ayuUsesTelegramTheme = true\n",
        "                ayuUsesTelegramTheme = false\n",
        "            ayuUsesTelegramTheme = false\n",
    ):
        text = text.replace(line, "")

    if "let ayuUsesTelegramTheme" in text or "ayuUsesTelegramTheme =" in text:
        raise RuntimeError("deleted visual compile fix: stale ayuUsesTelegramTheme code remains")

    path.write_text(text, encoding="utf-8")
    print("[ayu-deleted-visual-compile-fix] removed dead Telegram-theme flag")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
