#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_EDIT_HISTORY_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_edit_history.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    manager = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    text = manager.read_text(encoding="utf-8")

    if MARK in text:
        print(f"[ayu-spy-edit-history] already patched: {manager}")
        return 0

    schema_anchor = '        _ = database.execute("CREATE TABLE IF NOT EXISTS attachments (peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, resource_id TEXT NOT NULL, kind TEXT NOT NULL, relative_path TEXT, local_saved INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(peer_id, message_namespace, message_id, resource_id))")\n'
    schema_new = schema_anchor + '''        // AYU_SPY_EDIT_HISTORY_v0_3: append-only edit revisions. Each remote edit\n        // stores the previous local text and the exact receive timestamp. No chat\n        // scanning/polling is used; writes happen only when Telegram delivers an edit.\n        _ = database.execute("CREATE TABLE IF NOT EXISTS edit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, edited_at INTEGER NOT NULL, previous_text TEXT NOT NULL)")\n        _ = database.execute("CREATE INDEX IF NOT EXISTS edit_history_message_idx ON edit_history(peer_id, message_namespace, message_id, edited_at DESC)")\n'''
    text = one(text, schema_anchor, schema_new, "edit-history schema")

    store_anchor = '''    private func store(snapshot: AyuDeletedArchiveSnapshot, mediaBox: MediaBox) {\n'''
    edit_methods = '''    func enqueueEdit(message: Message) {\n        guard AyuRuntimeSettings.snapshot.saveEditHistory else {\n            return\n        }\n        let peerId = message.id.peerId.toInt64()\n        let namespace = message.id.namespace\n        let messageId = message.id.id\n        let editedAt = Int64(Date().timeIntervalSince1970)\n        let previousText = message.text\n\n        self.queue.async { [weak self] in\n            guard let self, let (_, database) = self.prepare() else {\n                return\n            }\n            _ = database.execute("INSERT INTO edit_history(peer_id, message_namespace, message_id, edited_at, previous_text) VALUES (\\(peerId), \\(namespace), \\(messageId), \\(editedAt), \\(self.sql(previousText)))")\n        }\n    }\n\n'''
    text = one(text, store_anchor, edit_methods + store_anchor, "edit-history writer")

    add_updates_anchor = '''        func addUpdates(_ updates: Api.Updates) {\n            self.queue.async {\n                self.updateService?.addUpdates(updates)\n            }\n        }\n'''
    add_updates_new = '''        func addUpdates(_ updates: Api.Updates) {\n            self.queue.async {\n                // AYU_SPY_EDIT_HISTORY_v0_3: snapshot the old Postbox message before\n                // UpdateMessageService replaces it with updateEditMessage data. The\n                // transaction is only used when an actual edit update is present.\n                if AyuRuntimeSettings.snapshot.saveEditHistory {\n                    var editedIds = Set<MessageId>()\n                    for update in updates.allUpdates {\n                        switch update {\n                        case .updateEditMessage, .updateEditChannelMessage:\n                            if let id = update.message?.id() {\n                                editedIds.insert(id)\n                            }\n                        default:\n                            break\n                        }\n                    }\n\n                    if !editedIds.isEmpty {\n                        let _ = self.postbox.transaction { transaction -> Void in\n                            for id in editedIds {\n                                if let currentMessage = transaction.getMessage(id) {\n                                    AyuDeletedArchive.shared.enqueueEdit(message: currentMessage)\n                                }\n                            }\n                        }.start(completed: { [weak self] in\n                            self?.queue.async { [weak self] in\n                                self?.updateService?.addUpdates(updates)\n                            }\n                        })\n                        return\n                    }\n                }\n                self.updateService?.addUpdates(updates)\n            }\n        }\n'''
    text = one(text, add_updates_anchor, add_updates_new, "edit-update interception")

    manager.write_text(text, encoding="utf-8")
    print("[ayu-spy-edit-history] event-driven edit history installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
