#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARK = "AYU_MANUAL_READ_PULSE_v0_3"


def die(message: str) -> None:
    print(f"[ayu-manual-read-pulse] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        die(f"{label}: expected exactly once, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reuse the 0.2 s Ghost online pulse for explicit manual Read")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.repo).expanduser().resolve()

    enqueue = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    context_menu = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    for path in (enqueue, context_menu):
        if not path.exists():
            die(f"missing file: {path}")

    enqueue_text = enqueue.read_text(encoding="utf-8")
    menu_text = context_menu.read_text(encoding="utf-8")

    # apply_ayu_send_read.py now performs this patch in the normal CI path.
    # Keep this standalone patcher idempotent for verifier/local use.
    if "public func ayuGhostOnlinePulse(account: Account)" not in enqueue_text:
        enqueue_text = replace_once(
            enqueue_text,
            "private func ayuSendOnlinePulse(account: Account) {",
            "public func ayuGhostOnlinePulse(account: Account) {",
            "pulse helper visibility",
        )
        enqueue_text = replace_once(
            enqueue_text,
            "    ayuSendOnlinePulse(account: account)\n",
            "    ayuGhostOnlinePulse(account: account)\n",
            "send pulse call",
        )
        enqueue.write_text(enqueue_text, encoding="utf-8")

    if MARK not in menu_text:
        old = """                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n"""
        new = """                // AYU_MANUAL_READ_PULSE_v0_3: explicit Read briefly uses\n                // the same 200 ms online pulse as sending, then Ghost returns offline.\n                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n"""
        menu_text = replace_once(menu_text, old, new, "manual Read action")
        context_menu.write_text(menu_text, encoding="utf-8")

    print("[ayu-manual-read-pulse] ready")


if __name__ == "__main__":
    main()
