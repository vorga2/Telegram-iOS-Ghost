#!/usr/bin/env python3
from pathlib import Path
import sys


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_behavior_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()

    # Manual Read: apply the selected MessageIndex directly in TelegramCore so
    # the selected incoming item and all older items above it become read locally,
    # then the existing one-shot Ghost allowance lets that max index sync.
    enqueue = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    t = enqueue.read_text(encoding="utf-8")
    anchor = "public func enqueueMessages(account: Account, peerId: PeerId, messages: [EnqueueMessage]) -> Signal<[MessageId?], NoError> {\n"
    helper = '''// AYU_BEHAVIOR_HOTFIX_v0_3\npublic func ayuReadMessageThroughGhost(account: Account, index: MessageIndex) {\n    guard AyuRuntimeSettings.snapshot.master else { return }\n    AyuRuntimeSettings.allowNextRead(peerId: index.id.peerId)\n    let _ = account.postbox.transaction { transaction -> Void in\n        _internal_applyMaxReadIndexInteractively(transaction: transaction, stateManager: account.stateManager, index: index)\n    }.start()\n}\n\n'''
    if "AYU_BEHAVIOR_HOTFIX_v0_3" not in t:
        t = one(t, anchor, helper + anchor, "read helper")
    enqueue.write_text(t, encoding="utf-8")

    menu = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    t = menu.read_text(encoding="utf-8")
    old_read = '''                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n'''
    if old_read not in t:
        old_read = '''                // AYU_MANUAL_READ_PULSE_v0_3: explicit Read briefly uses\n                // the same 200 ms online pulse as sending, then Ghost returns offline.\n                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                ayuGhostOnlinePulse(account: context.account)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n'''
    new_read = '''                ayuGhostOnlinePulse(account: context.account)\n                ayuReadMessageThroughGhost(account: context.account, index: ayuMessage.index)\n'''
    if "ayuReadMessageThroughGhost(account: context.account" not in t:
        t = one(t, old_read, new_read, "manual Read")

    # Burn is remote-only: notify Telegram that the view-once content was consumed,
    # but keep the local message/media/durable copy intact. Also pulse online 0.2 s.
    old_burn = '''                AyuRuntimeSettings.allowNextViewOnceBurn(ayuBurnMessage.id)\n                let _ = context.engine.messages.markMessageContentAsConsumedInteractively(messageId: ayuBurnMessage.id).startStandalone()\n'''
    new_burn = '''                ayuGhostOnlinePulse(account: context.account)\n                let _ = ayuBurnViewOnceRemotely(account: context.account, messageId: ayuBurnMessage.id).startStandalone()\n'''
    if "ayuBurnViewOnceRemotely(account: context.account" not in t:
        t = one(t, old_burn, new_burn, "Burn action")
    menu.write_text(t, encoding="utf-8")

    consume = root / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift"
    t = consume.read_text(encoding="utf-8")
    consume_anchor = "func _internal_markMessageContentAsConsumedInteractively(postbox: Postbox, messageId: MessageId) -> Signal<Void, NoError> {\n"
    burn_helper = '''public func ayuBurnViewOnceRemotely(account: Account, messageId: MessageId) -> Signal<Void, NoError> {\n    return account.postbox.transaction { transaction -> Void in\n        guard let message = transaction.getMessage(messageId), AyuRuntimeSettings.shouldPreserveViewOnce(message: message) else { return }\n        addSynchronizeConsumeMessageContentsOperation(transaction: transaction, messageIds: [messageId])\n    }\n}\n\n'''
    if "public func ayuBurnViewOnceRemotely" not in t:
        t = one(t, consume_anchor, burn_helper + consume_anchor, "remote Burn helper")

    remote_anchor = "func markMessageContentAsConsumedRemotely(transaction: Transaction, messageId: MessageId, consumeDate: Int32?) {\n    if let message = transaction.getMessage(messageId) {\n"
    remote_new = "func markMessageContentAsConsumedRemotely(transaction: Transaction, messageId: MessageId, consumeDate: Int32?) {\n    if let message = transaction.getMessage(messageId) {\n        if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n            return\n        }\n"
    if "if AyuRuntimeSettings.shouldPreserveViewOnce(message: message) {\n            return\n        }\n        var updateMessage" not in t:
        t = one(t, remote_anchor, remote_new, "remote consume preservation")
    consume.write_text(t, encoding="utf-8")

    # A same-value StoreMessage update can be coalesced. Change one private local
    # tag bit so Postbox emits a real history-view update immediately; rendering
    # still uses AyuRuntimeSettings.isDeleted(id), so the tag has no UI semantics.
    manager = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    t = manager.read_text(encoding="utf-8")
    old_tags = "                            localTags: currentMessage.localTags,\n"
    new_tags = '''                            localTags: currentMessage.localTags.union(LocalMessageTags(rawValue: 1 << 30)),\n'''
    if "LocalMessageTags(rawValue: 1 << 30)" not in t:
        t = one(t, old_tags, new_tags, "deleted realtime local tag")
    manager.write_text(t, encoding="utf-8")

    print("[ayu-behavior-hotfix] manual Read + remote Burn + realtime deleted refresh patched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
