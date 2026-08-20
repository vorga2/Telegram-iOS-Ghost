#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_RUNTIME_CORRECTNESS_v0_3"
HISTORY_MARK = "AYU_CANONICAL_EDIT_HISTORY_v0_3"
LIVE_MARK = "AYU_DELETED_STABLE_REFRESH_v0_3"
VISUAL_MARK = "AYU_STOCK_BUBBLE_ALPHA_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def function_bounds(text: str, signature: str) -> tuple[int, int]:
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"function anchor missing: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"function opening brace missing: {signature}")
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise RuntimeError(f"function closing brace missing: {signature}")


def patch_history(manager: str) -> str:
    if HISTORY_MARK not in manager:
        store_anchor = "    private func store(snapshot: AyuDeletedArchiveSnapshot, mediaBox: MediaBox) {\n"
        helper = r'''    // AYU_CANONICAL_EDIT_HISTORY_v0_3
    // Capture the previous text in the exact Postbox transaction that is about
    // to replay Telegram's canonical EditMessage mutation. This catches raw
    // updates, getDifference and channel synchronization without polling.
    func captureEditsBeforeReplay(state: AccountMutableState, transaction: Transaction) {
        guard AyuRuntimeSettings.snapshot.saveEditHistory else {
            return
        }

        var touched = Set<MessageId>()
        for operation in state.operations {
            guard case let .EditMessage(messageId, updatedMessage) = operation else {
                continue
            }
            guard touched.insert(messageId).inserted else {
                continue
            }
            guard let currentMessage = transaction.getMessage(messageId) else {
                continue
            }
            // The requested History menu is for the interlocutor's messages.
            guard currentMessage.flags.contains(.Incoming) else {
                continue
            }
            // Do not write a revision for metadata-only edits.
            guard currentMessage.text != updatedMessage.text else {
                continue
            }
            self.enqueueEdit(message: currentMessage)
        }
    }

'''
        manager = one(manager, store_anchor, helper + store_anchor, "canonical edit-history helper")

    # Remove the old raw-only interception. Besides missing difference/channel
    # edits it delayed forwarding the Api.Updates object. Deleted-message raw
    # refresh remains intact and the normal Telegram update path resumes at once.
    add_signature = "        func addUpdates(_ updates: Api.Updates) {"
    start, end = function_bounds(manager, add_signature)
    add_function = manager[start:end]
    if "AYU_SPY_EDIT_HISTORY_v0_3: snapshot the old Postbox message" in add_function:
        replacement = '''        func addUpdates(_ updates: Api.Updates) {
            self.queue.async {
                self.ayuRefreshPreservedDeletedMessages(updates)
                self.updateService?.addUpdates(updates)
            }
        }'''
        manager = manager[:start] + replacement + manager[end:]

    # Every canonical replay that already has an AccountMutableState is patched
    # just before replayFinalState. This adds work only when Telegram is applying
    # an update batch; it has zero render/frame-loop cost.
    call_token = "replayFinalState("
    positions: list[int] = []
    search_from = 0
    while True:
        pos = manager.find(call_token, search_from)
        if pos < 0:
            break
        positions.append(pos)
        search_from = pos + len(call_token)

    inserted = 0
    for pos in reversed(positions):
        line_start = manager.rfind("\n", 0, pos) + 1
        line_prefix = manager[line_start:pos]
        # We only patch actual calls, not a declaration if upstream ever adds one.
        if "=" not in line_prefix and "return " not in line_prefix:
            continue
        lookahead = manager[pos:pos + 2600]
        if "finalState: finalState" in lookahead:
            state_expr = "finalState.state"
        elif "finalState: AccountFinalState(" in lookahead and "state: finalMutableState" in lookahead:
            state_expr = "finalMutableState"
        else:
            continue

        previous = manager[max(0, line_start - 240):line_start]
        if "captureEditsBeforeReplay" in previous:
            continue
        indent = manager[line_start:line_start + len(manager[line_start:]) - len(manager[line_start:].lstrip(" \t"))]
        capture = f"{indent}AyuDeletedArchive.shared.captureEditsBeforeReplay(state: {state_expr}, transaction: transaction)\n"
        manager = manager[:line_start] + capture + manager[line_start:]
        inserted += 1

    if HISTORY_MARK in manager and manager.count("captureEditsBeforeReplay(state:") < 2:
        raise RuntimeError("canonical edit-history replay hooks missing")
    if inserted == 0 and manager.count("captureEditsBeforeReplay(state:") < 2:
        raise RuntimeError("no canonical replay hooks inserted")
    return manager


def patch_live_deleted(manager: str) -> str:
    stable_value = "UInt32(bitPattern: currentMessage.id.id) ^ 0xA5A5A5A5"

    raw_signature = "        private func ayuRefreshPreservedDeletedMessages(_ updates: Api.Updates) {"
    raw_start, raw_end = function_bounds(manager, raw_signature)
    raw = manager[raw_start:raw_end]
    if LIVE_MARK not in raw:
        anchor = "                            customStableId: nil,\n"
        if raw.count(anchor) != 1:
            raise RuntimeError(f"raw deleted customStableId anchor expected 1, found {raw.count(anchor)}")
        raw = raw.replace(
            anchor,
            f"                            // {LIVE_MARK}\n                            customStableId: {stable_value},\n",
            1,
        )
        manager = manager[:raw_start] + raw + manager[raw_end:]

    final_signature = "        private func ayuRefreshPreservedDeletedEventIds(_ deletedIds: [DeletedMessageId]) {"
    final_start, final_end = function_bounds(manager, final_signature)
    final = manager[final_start:final_end]
    if LIVE_MARK not in final:
        anchor = "                            customStableId: nil,\n"
        if final.count(anchor) != 1:
            raise RuntimeError(f"final deleted customStableId anchor expected 1, found {final.count(anchor)}")
        final = final.replace(
            anchor,
            f"                            // {LIVE_MARK}\n                            customStableId: {stable_value},\n",
            1,
        )
        manager = manager[:final_start] + final + manager[final_end:]

    if manager.count(stable_value) < 2:
        raise RuntimeError("live deleted stable-id refresh missing")
    return manager


def patch_visuals(root: Path) -> None:
    bubble_path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    bubble = bubble_path.read_text(encoding="utf-8")

    visible_old = '''        let ayuDeletedBackgroundColor: UIColor?\n        if AyuRuntimeSettings.isDeleted(item.message.id) && !AyuRuntimeSettings.isInDeletedViewer(item.message.id) {\n'''
    visible_new = '''        // AYU_STOCK_BUBBLE_ALPHA_v0_3: compute the tombstone once per item layout.\n        let ayuDeletedVisible = AyuRuntimeSettings.isDeleted(item.message.id) && !AyuRuntimeSettings.isInDeletedViewer(item.message.id)\n        let ayuDeletedBackgroundColor: UIColor?\n        if ayuDeletedVisible {\n'''
    if VISUAL_MARK not in bubble:
        bubble = one(bubble, visible_old, visible_new, "deleted visible layout state")

    alpha_old = '''        strongSelf.backgroundNode.alpha = 1.0\n        strongSelf.backgroundWallpaperNode.alpha = 1.0\n'''
    alpha_new = '''        // Telegram-theme deleted messages keep the exact stock bubble image/color.\n        // Only the two bubble-background nodes are composited at 0.5; text, media,\n        // status and controls remain stock opacity. No image tint/cache work is used.\n        let ayuTelegramThemeDeleted = ayuDeletedVisible && ayuDeletedBackgroundColor == nil\n        strongSelf.backgroundNode.alpha = ayuTelegramThemeDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n        strongSelf.backgroundWallpaperNode.alpha = ayuTelegramThemeDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n'''
    if "let ayuTelegramThemeDeleted" not in bubble:
        bubble = one(bubble, alpha_old, alpha_new, "stock Telegram deleted bubble alpha")
    bubble_path.write_text(bubble, encoding="utf-8")

    item_path = root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift"
    item = item_path.read_text(encoding="utf-8")
    initial = '''            let ayuDeletedWholeItem = AyuRuntimeSettings.isDeleted(self.message.id) && !AyuRuntimeSettings.isInDeletedViewer(self.message.id)\n            node.alpha = ayuDeletedWholeItem ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n'''
    reuse = '''                                let ayuDeletedWholeItem = AyuRuntimeSettings.isDeleted(self.message.id) && !AyuRuntimeSettings.isInDeletedViewer(self.message.id)\n                                nodeValue.alpha = ayuDeletedWholeItem ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n'''
    if initial in item:
        item = item.replace(initial, "            node.alpha = 1.0\n", 1)
    if reuse in item:
        item = item.replace(reuse, "                                nodeValue.alpha = 1.0\n", 1)
    if "ayuDeletedWholeItem" in item:
        raise RuntimeError("whole-message deleted alpha still present")
    item_path.write_text(item, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_runtime_correctness_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    manager_path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    manager = manager_path.read_text(encoding="utf-8")
    manager = patch_history(manager)
    manager = patch_live_deleted(manager)
    if MARK not in manager:
        anchor = "private enum AccountStateManagerOperationContent {\n"
        manager = one(manager, anchor, f"// {MARK}\n" + anchor, "runtime correctness marker")
    manager_path.write_text(manager, encoding="utf-8")

    patch_visuals(root)

    print("[ayu-runtime-correctness] canonical edit history + one-shot live deleted rebuild + stock bubble 0.5 alpha installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
