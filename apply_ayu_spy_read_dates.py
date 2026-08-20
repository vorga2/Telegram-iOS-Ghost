#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_READ_DATES_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_read_dates.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
    text = path.read_text(encoding="utf-8")

    if MARK in text:
        print(f"[ayu-spy-read-dates] already patched: {path}")
        return 0

    helper_anchor = "private func reactionGeneratedEvent("
    helper = r'''// AYU_SPY_READ_DATES_v0_3
// Local fallback read timestamps for outgoing messages. We store only monotonic
// max-read events, not one row per message, so there is no history scan and very
// little disk traffic. Details can later resolve a message to the earliest event
// whose max_message_id covers it.
private final class AyuSpyReadDateArchive {
    static let shared = AyuSpyReadDateArchive()

    private let queue = Queue(name: "ayu.spy.read-dates")
    private var database: Database?

    private init() {
    }

    private func prepare() -> Database? {
        if let database = self.database {
            return database
        }
        guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
            return nil
        }
        let deleted = documents
            .appendingPathComponent("AyuGram", isDirectory: true)
            .appendingPathComponent("Deleted", isDirectory: true)
        try? FileManager.default.createDirectory(at: deleted, withIntermediateDirectories: true)

        let path = deleted.appendingPathComponent("deleted.sqlite").path
        guard let database = Database(path, readOnly: false) else {
            return nil
        }
        _ = database.execute("PRAGMA journal_mode=WAL")
        _ = database.execute("PRAGMA synchronous=NORMAL")
        _ = database.execute("CREATE TABLE IF NOT EXISTS read_receipts (peer_id INTEGER NOT NULL, max_message_id INTEGER NOT NULL, read_at INTEGER NOT NULL, UNIQUE(peer_id, max_message_id))")
        _ = database.execute("CREATE INDEX IF NOT EXISTS read_receipts_lookup_idx ON read_receipts(peer_id, max_message_id, read_at)")
        self.database = database
        return database
    }

    func enqueue(peerId: PeerId, maxMessageId: Int32) {
        guard AyuRuntimeSettings.snapshot.saveReadDates else {
            return
        }
        // Channels use separate read state semantics and are intentionally excluded.
        guard peerId.namespace != Namespaces.Peer.CloudChannel else {
            return
        }

        let peer = peerId.toInt64()
        let readAt = Int64(Date().timeIntervalSince1970)
        self.queue.async { [weak self] in
            guard let self, let database = self.prepare() else {
                return
            }
            // Preserve the first time we observed this exact max-read boundary.
            _ = database.execute("INSERT OR IGNORE INTO read_receipts(peer_id, max_message_id, read_at) VALUES (\(peer), \(maxMessageId), \(readAt))")
        }
    }
}

'''
    text = one(text, helper_anchor, helper + helper_anchor, "read-date helper")

    read_anchor = '''            case let .updateReadHistoryOutbox(updateReadHistoryOutboxData):
                updatedState.readOutbox(MessageId(peerId: updateReadHistoryOutboxData.peer.peerId, namespace: Namespaces.Message.Cloud, id: updateReadHistoryOutboxData.maxId), timestamp: updatesDate)
'''
    read_new = '''            case let .updateReadHistoryOutbox(updateReadHistoryOutboxData):
                let ayuReadMessageId = MessageId(peerId: updateReadHistoryOutboxData.peer.peerId, namespace: Namespaces.Message.Cloud, id: updateReadHistoryOutboxData.maxId)
                updatedState.readOutbox(ayuReadMessageId, timestamp: updatesDate)
                AyuSpyReadDateArchive.shared.enqueue(peerId: ayuReadMessageId.peerId, maxMessageId: ayuReadMessageId.id)
'''
    text = one(text, read_anchor, read_new, "outgoing read update")

    path.write_text(text, encoding="utf-8")
    print("[ayu-spy-read-dates] local private/group read-date ranges installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
