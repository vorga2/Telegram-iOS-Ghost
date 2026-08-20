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
    schema_new = schema_anchor + '''        // AYU_SPY_EDIT_HISTORY_v0_3: append-only edit revisions. Each remote edit
        // stores the previous local text and the exact receive timestamp. No chat
        // scanning/polling is used; writes happen only when Telegram delivers an edit.
        _ = database.execute("CREATE TABLE IF NOT EXISTS edit_history (id INTEGER PRIMARY KEY AUTOINCREMENT, peer_id INTEGER NOT NULL, message_namespace INTEGER NOT NULL, message_id INTEGER NOT NULL, edited_at INTEGER NOT NULL, previous_text TEXT NOT NULL)")
        _ = database.execute("CREATE INDEX IF NOT EXISTS edit_history_message_idx ON edit_history(peer_id, message_namespace, message_id, edited_at DESC)")
'''
    text = one(text, schema_anchor, schema_new, "edit-history schema")

    store_anchor = '''    private func store(snapshot: AyuDeletedArchiveSnapshot, mediaBox: MediaBox) {
'''
    edit_methods = '''    func enqueueEdit(message: Message) {
        guard AyuRuntimeSettings.snapshot.saveEditHistory else {
            return
        }
        let peerId = message.id.peerId.toInt64()
        let namespace = message.id.namespace
        let messageId = message.id.id
        let editedAt = Int64(Date().timeIntervalSince1970)
        let previousText = message.text

        self.queue.async { [weak self] in
            guard let self, let (_, database) = self.prepare() else {
                return
            }
            _ = database.execute("INSERT INTO edit_history(peer_id, message_namespace, message_id, edited_at, previous_text) VALUES (\(peerId), \(namespace), \(messageId), \(editedAt), \(self.sql(previousText)))")
        }
    }

'''
    text = one(text, store_anchor, edit_methods + store_anchor, "edit-history writer")

    add_updates_anchor = '''        func addUpdates(_ updates: Api.Updates) {
            self.queue.async {
                self.ayuRefreshPreservedDeletedMessages(updates)
                self.updateService?.addUpdates(updates)
            }
        }
'''
    add_updates_new = '''        func addUpdates(_ updates: Api.Updates) {
            self.queue.async {
                self.ayuRefreshPreservedDeletedMessages(updates)

                // AYU_SPY_EDIT_HISTORY_v0_3: snapshot the old Postbox message before
                // UpdateMessageService replaces it with updateEditMessage data. The
                // transaction is only used when an actual edit update is present.
                if AyuRuntimeSettings.snapshot.saveEditHistory {
                    var editedIds = Set<MessageId>()
                    for update in updates.allUpdates {
                        switch update {
                        case .updateEditMessage, .updateEditChannelMessage:
                            if let id = update.message?.id() {
                                editedIds.insert(id)
                            }
                        default:
                            break
                        }
                    }

                    if !editedIds.isEmpty {
                        let _ = self.postbox.transaction { transaction -> Void in
                            for id in editedIds {
                                if let currentMessage = transaction.getMessage(id) {
                                    AyuDeletedArchive.shared.enqueueEdit(message: currentMessage)
                                }
                            }
                        }.start(completed: { [weak self] in
                            self?.queue.async { [weak self] in
                                self?.updateService?.addUpdates(updates)
                            }
                        })
                        return
                    }
                }
                self.updateService?.addUpdates(updates)
            }
        }
'''
    text = one(text, add_updates_anchor, add_updates_new, "edit-update interception")

    manager.write_text(text, encoding="utf-8")
    print("[ayu-spy-edit-history] event-driven edit history installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
