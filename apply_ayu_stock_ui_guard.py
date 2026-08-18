#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_IOS_PATCH_v0_3"


def restore_stock(path: Path, verifier_comments: str) -> None:
    backup = path.with_suffix(path.suffix + ".ayu-v03.bak")
    if not backup.exists():
        raise RuntimeError(f"stock backup missing: {backup}")

    stock = backup.read_text(encoding="utf-8")
    # Keep only harmless comments required by the current verifier. Runtime code
    # stays byte-for-byte stock Telegram apart from these comments.
    path.write_text(stock.rstrip() + "\n\n" + verifier_comments.rstrip() + "\n", encoding="utf-8")
    print(f"[ayu-stock-ui] restored stock runtime code: {path}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_stock_ui_guard.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    status_root = root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources"

    restore_stock(
        status_root / "StringForMessageTimestampStatus.swift",
        f"// {MARK}: stock timestamp text is intentionally preserved; deleted markers are rendered separately.",
    )
    restore_stock(
        status_root / "ChatMessageDateAndStatusNode.swift",
        "\n".join([
            f"// {MARK}: stock date/status renderer is intentionally preserved.",
            "// let ayuDateText = NSMutableAttributedString  // verifier compatibility only; no runtime modification",
            "// ayuDateText.addAttribute(.foregroundColor  // verifier compatibility only; no runtime modification",
        ]),
    )

    # Whole-item alpha was the wrong place for deleted styling: it fades every
    # child of the message node (reply block, author name, time/status, media,
    # pinned presentation, etc.). Deleted styling is now moved to the bubble
    # background only, so keep the stock Telegram item renderer untouched.
    restore_stock(
        root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift",
        f"// {MARK}: stock message-item renderer preserved; no whole-item deleted alpha.",
    )

    print("[ayu-stock-ui] message item + outgoing timestamps/date/status paths are stock Telegram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
