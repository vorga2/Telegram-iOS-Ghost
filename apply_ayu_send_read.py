#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

MARK = "AYU_SEND_READ_v0_3"


def die(message: str) -> None:
    print(f"[ayu-send-read] ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the current peer when sending while Ghost is active")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    path = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    if not path.exists():
        die(f"missing file: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print(f"[ayu-send-read] already patched: {path}")
        return

    anchor = "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n    ayuSendOnlinePulse(account: account)\n"
    if text.count(anchor) != 1:
        die(f"enqueue anchor expected exactly once, found {text.count(anchor)}")

    helper = r'''
// AYU_SEND_READ_v0_3: sending is an explicit interaction, so while Ghost is on
// we read the current peer even if passive read receipts are suppressed.
// One Postbox transaction per send action; no timer, polling or history scan.
private func ayuReadPeerOnSend(account: Account, peerId: PeerId) {
    guard AyuRuntimeSettings.snapshot.master else {
        return
    }

    let _ = account.postbox.transaction { transaction -> Void in
        guard let index = transaction.getTopPeerMessageIndex(peerId: peerId) else {
            return
        }

        // Reuse the same one-shot bypass as the explicit "Прочитать" action.
        // The synchronization layer consumes it only when an actual push occurs.
        AyuRuntimeSettings.allowNextRead(peerId: peerId)
        _internal_applyMaxReadIndexInteractively(
            transaction: transaction,
            stateManager: account.stateManager,
            index: index
        )
    }.start()
}

'''

    replacement = helper + "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n    ayuSendOnlinePulse(account: account)\n    ayuReadPeerOnSend(account: account, peerId: peerId)\n"
    path.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
    print(f"[ayu-send-read] patched: {path}")


if __name__ == "__main__":
    main()
