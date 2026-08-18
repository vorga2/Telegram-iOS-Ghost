#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_CONTENT_READ_DATES_v0_4"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_spy_content_read_dates.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # Telegram delivers content-consumed updates separately from ordinary outbox
    # reads. Persist first-seen content-read timestamps with peer-qualified keys so
    # supergroups are safe too. Broadcast channels are deliberately excluded.
    state_utils = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
    text = state_utils.read_text(encoding="utf-8")
    if MARK not in text:
        helper_anchor = "private func reactionGeneratedEvent("
        helper = r'''// AYU_SPY_CONTENT_READ_DATES_v0_4 / AYU_SPY_CONTENT_READ_DATES_v0_3 compatibility
private final class AyuSpyContentReadDateArchive {
    static let shared = AyuSpyContentReadDateArchive()

    private let queue = Queue(name: "ayu.spy.content-read-dates")
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
        let deleted = documents.appendingPathComponent("Deleted", isDirectory: true)
        try? FileManager.default.createDirectory(at: deleted, withIntermediateDirectories: true)

        let path = deleted.appendingPathComponent("deleted.sqlite").path
        guard let database = Database(path, readOnly: false) else {
            return nil
        }
        _ = database.execute("PRAGMA journal_mode=WAL")
        _ = database.execute("PRAGMA synchronous=NORMAL")
        // Keep the v1 table untouched for compatibility with already-installed test
        // builds, but all new writes use peer-qualified v2 rows.
        _ = database.execute("CREATE TABLE IF NOT EXISTS content_read_receipts (global_message_id INTEGER PRIMARY KEY, read_at INTEGER NOT NULL)")
        _ = database.execute("CREATE TABLE IF NOT EXISTS content_read_receipts_v2 (peer_id INTEGER NOT NULL, message_id INTEGER NOT NULL, read_at INTEGER NOT NULL, PRIMARY KEY(peer_id, message_id))")
        _ = database.execute("CREATE INDEX IF NOT EXISTS content_read_receipts_v2_lookup_idx ON content_read_receipts_v2(peer_id, message_id, read_at)")
        self.database = database
        return database
    }

    private func enqueueWrite(messageIds: [MessageId], readAt: Int64) {
        guard !messageIds.isEmpty else {
            return
        }
        let uniqueIds = Array(Set(messageIds))
        self.queue.async { [weak self] in
            guard let self, let database = self.prepare() else {
                return
            }
            for id in uniqueIds {
                _ = database.execute("INSERT OR IGNORE INTO content_read_receipts_v2(peer_id, message_id, read_at) VALUES (\(id.peerId.toInt64()), \(id.id), \(readAt))")
            }
        }
    }

    func enqueueGlobal(postbox: Postbox, globalMessageIds: [Int32], serverTimestamp: Int32?) {
        guard AyuRuntimeSettings.snapshot.saveReadDates, !globalMessageIds.isEmpty else {
            return
        }
        let readAt = Int64(serverTimestamp ?? Int32(Date().timeIntervalSince1970))
        let ids = Array(Set(globalMessageIds))
        let _ = (postbox.transaction { transaction -> [MessageId] in
            return transaction.messageIdsForGlobalIds(ids)
        }
        |> take(1)).start(next: { [weak self] messageIds in
            self?.enqueueWrite(messageIds: messageIds, readAt: readAt)
        })
    }

    func enqueueChannel(postbox: Postbox, peerId: PeerId, messageIds: [Int32], serverTimestamp: Int32?) {
        guard AyuRuntimeSettings.snapshot.saveReadDates, !messageIds.isEmpty else {
            return
        }
        let readAt = Int64(serverTimestamp ?? Int32(Date().timeIntervalSince1970))
        let ids = Array(Set(messageIds))

        let _ = (postbox.transaction { transaction -> Bool in
            guard let channel = transaction.getPeer(peerId) as? TelegramChannel else {
                return false
            }
            if case .group = channel.info {
                return true
            } else {
                return false
            }
        }
        |> take(1)).start(next: { [weak self] shouldStore in
            guard shouldStore else {
                return
            }
            self?.enqueueWrite(
                messageIds: ids.map { MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0) },
                readAt: readAt
            )
        })
    }
}

'''
        text = one(text, helper_anchor, helper + helper_anchor, "content-read helper")

        generic_old = '''            case let .updateReadMessagesContents(updateReadMessagesContentsData):
                updatedState.addReadMessagesContents((nil, nil, updateReadMessagesContentsData.messages), date: updateReadMessagesContentsData.date)
'''
        generic_new = '''            case let .updateReadMessagesContents(updateReadMessagesContentsData):
                updatedState.addReadMessagesContents((nil, nil, updateReadMessagesContentsData.messages), date: updateReadMessagesContentsData.date)
                AyuSpyContentReadDateArchive.shared.enqueueGlobal(postbox: postbox, globalMessageIds: updateReadMessagesContentsData.messages, serverTimestamp: updateReadMessagesContentsData.date ?? serverTime)
'''
        count = text.count(generic_old)
        if count < 1:
            raise RuntimeError(f"content-read generic update: expected at least 1 anchor, found {count}")
        text = text.replace(generic_old, generic_new)

        channel_old = '''                updatedState.addReadMessagesContents((PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(channelId)), threadId, messages), date: nil)
'''
        channel_new = '''                let ayuContentReadPeerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(channelId))
                updatedState.addReadMessagesContents((ayuContentReadPeerId, threadId, messages), date: nil)
                AyuSpyContentReadDateArchive.shared.enqueueChannel(postbox: postbox, peerId: ayuContentReadPeerId, messageIds: messages, serverTimestamp: serverTime)
'''
        count = text.count(channel_old)
        if count < 1:
            raise RuntimeError(f"content-read channel update: expected at least 1 anchor, found {count}")
        text = text.replace(channel_old, channel_new)
        state_utils.write_text(text, encoding="utf-8")

    # Extend the indexed Details lookup created by apply_ayu_spy_details.py.
    manager = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    text = manager.read_text(encoding="utf-8")
    if "localContentReadAt" not in text:
        old_struct = '''public struct AyuSpyStoredMessageDetails {
    public let deletedAt: Int64?
    public let localReadAt: Int64?

    public init(deletedAt: Int64?, localReadAt: Int64?) {
        self.deletedAt = deletedAt
        self.localReadAt = localReadAt
    }
}
'''
        new_struct = '''public struct AyuSpyStoredMessageDetails {
    public let deletedAt: Int64?
    public let localReadAt: Int64?
    public let localContentReadAt: Int64?

    public init(deletedAt: Int64?, localReadAt: Int64?, localContentReadAt: Int64?) {
        self.deletedAt = deletedAt
        self.localReadAt = localReadAt
        self.localContentReadAt = localContentReadAt
    }
}
'''
        text = one(text, old_struct, new_struct, "stored details struct")
        text = text.replace(
            "return AyuSpyStoredMessageDetails(deletedAt: nil, localReadAt: nil)",
            "return AyuSpyStoredMessageDetails(deletedAt: nil, localReadAt: nil, localContentReadAt: nil)",
        )

        # Regular read fallback is valid for supergroups now. Broadcasts never get
        # rows because the writer resolves TelegramChannel.info and rejects them.
        old_regular = '''    if AyuRuntimeSettings.snapshot.saveReadDates && messageId.peerId.namespace != Namespaces.Peer.CloudChannel {
        let readRows = database.queryRows("SELECT read_at FROM read_receipts WHERE peer_id = \\(peerId) AND max_message_id >= \\(messageId.id) ORDER BY read_at ASC LIMIT 1")
'''
        new_regular = '''    if AyuRuntimeSettings.snapshot.saveReadDates {
        let readRows = database.queryRows("SELECT read_at FROM read_receipts WHERE peer_id = \\(peerId) AND max_message_id >= \\(messageId.id) ORDER BY read_at ASC LIMIT 1")
'''
        text = one(text, old_regular, new_regular, "supergroup regular-read Details fallback")

        old_return = '''    return AyuSpyStoredMessageDetails(deletedAt: deletedAt, localReadAt: localReadAt)
'''
        new_return = '''    var localContentReadAt: Int64?
    if AyuRuntimeSettings.snapshot.saveReadDates {
        let contentRows = database.queryRows("SELECT read_at FROM content_read_receipts_v2 WHERE peer_id = \(peerId) AND message_id = \(messageId.id) LIMIT 1")
        if let row = contentRows.first, let value = row.first ?? nil {
            localContentReadAt = Int64(value)
        } else if messageId.peerId.namespace != Namespaces.Peer.CloudChannel {
            // Upgrade fallback for test builds that wrote the old global-id table.
            let legacyRows = database.queryRows("SELECT read_at FROM content_read_receipts WHERE global_message_id = \(messageId.id) LIMIT 1")
            if let row = legacyRows.first, let value = row.first ?? nil {
                localContentReadAt = Int64(value)
            }
        }
    }

    return AyuSpyStoredMessageDetails(deletedAt: deletedAt, localReadAt: localReadAt, localContentReadAt: localContentReadAt)
'''
        text = one(text, old_return, new_return, "stored content-read query")
        manager.write_text(text, encoding="utf-8")

    # Voice messages and instant videos show true content-consumed time only. Do
    # not substitute the generic message read timestamp: those events are different.
    menu = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    text = menu.read_text(encoding="utf-8")
    if "effectiveContentReadAt" not in text:
        old_effective = '''    let effectiveReadAt = telegramReadAt ?? (AyuRuntimeSettings.snapshot.saveReadDates ? stored.localReadAt : nil)

    var didAddMediaDetails = false
'''
        new_effective = '''    let effectiveReadAt = telegramReadAt ?? (AyuRuntimeSettings.snapshot.saveReadDates ? stored.localReadAt : nil)
    let effectiveContentReadAt = AyuRuntimeSettings.snapshot.saveReadDates ? stored.localContentReadAt : nil

    var didAddMediaDetails = false
'''
        text = one(text, old_effective, new_effective, "content-read effective timestamp")

        old_media = '''            if (file.isVoice || file.isInstantVideo), let effectiveReadAt {
                items.append(ayuDetailsRow("Дата прочтения содержимого: \(ayuDetailsDate(effectiveReadAt))"))
'''
        new_media = '''            if (file.isVoice || file.isInstantVideo), let effectiveContentReadAt {
                items.append(ayuDetailsRow("Дата прочтения содержимого: \(ayuDetailsDate(effectiveContentReadAt))"))
'''
        text = one(text, old_media, new_media, "content-read Details row")
        menu.write_text(text, encoding="utf-8")

    print("[ayu-spy-content-read-dates] server-aware PM/group/supergroup content-read timestamps installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
