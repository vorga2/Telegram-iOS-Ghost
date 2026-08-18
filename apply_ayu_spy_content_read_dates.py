#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SPY_CONTENT_READ_DATES_v0_3"


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

    # Telegram delivers content-consumed updates separately from ordinary
    # outbox read-state updates. Keep one first-seen timestamp per global
    # non-channel message id. This is event-driven and does no chat scanning.
    state_utils = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
    text = state_utils.read_text(encoding="utf-8")
    if MARK not in text:
        helper_anchor = "private func reactionGeneratedEvent("
        helper = r'''// AYU_SPY_CONTENT_READ_DATES_v0_3
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
        _ = database.execute("CREATE TABLE IF NOT EXISTS content_read_receipts (global_message_id INTEGER PRIMARY KEY, read_at INTEGER NOT NULL)")
        self.database = database
        return database
    }

    func enqueue(globalMessageIds: [Int32]) {
        guard AyuRuntimeSettings.snapshot.saveReadDates, !globalMessageIds.isEmpty else {
            return
        }

        // The UI requirement is local phone time. Store one timestamp for the
        // whole Telegram update and preserve the first observation for each id.
        let readAt = Int64(Date().timeIntervalSince1970)
        let ids = Array(Set(globalMessageIds))
        self.queue.async { [weak self] in
            guard let self, let database = self.prepare() else {
                return
            }
            for id in ids {
                _ = database.execute("INSERT OR IGNORE INTO content_read_receipts(global_message_id, read_at) VALUES (\(id), \(readAt))")
            }
        }
    }
}

'''
        text = one(text, helper_anchor, helper + helper_anchor, "content-read helper")

        old = '''            case let .updateReadMessagesContents(updateReadMessagesContentsData):
                updatedState.addReadMessagesContents((nil, nil, updateReadMessagesContentsData.messages), date: updateReadMessagesContentsData.date)
'''
        new = '''            case let .updateReadMessagesContents(updateReadMessagesContentsData):
                updatedState.addReadMessagesContents((nil, nil, updateReadMessagesContentsData.messages), date: updateReadMessagesContentsData.date)
                AyuSpyContentReadDateArchive.shared.enqueue(globalMessageIds: updateReadMessagesContentsData.messages)
'''
        count = text.count(old)
        if count < 1:
            raise RuntimeError(f"content-read update: expected at least 1 anchor, found {count}")
        # This case can exist in more than one Telegram update-processing path.
        # Patch every occurrence; INSERT OR IGNORE keeps the first read timestamp.
        text = text.replace(old, new)
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

        old_return = '''    return AyuSpyStoredMessageDetails(deletedAt: deletedAt, localReadAt: localReadAt)
'''
        new_return = '''    var localContentReadAt: Int64?
    if AyuRuntimeSettings.snapshot.saveReadDates && messageId.peerId.namespace != Namespaces.Peer.CloudChannel {
        let contentRows = database.queryRows("SELECT read_at FROM content_read_receipts WHERE global_message_id = \(messageId.id) LIMIT 1")
        localContentReadAt = contentRows.first?.first.flatMap { $0 }.flatMap(Int64.init)
    }

    return AyuSpyStoredMessageDetails(deletedAt: deletedAt, localReadAt: localReadAt, localContentReadAt: localContentReadAt)
'''
        text = one(text, old_return, new_return, "stored content-read query")
        manager.write_text(text, encoding="utf-8")

    # Voice messages and instant videos use their content-consumed timestamp.
    # Ordinary text still uses the outbox read timestamp/fallback as before.
    menu = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    text = menu.read_text(encoding="utf-8")
    if "effectiveContentReadAt" not in text:
        old_effective = '''    let effectiveReadAt = telegramReadAt ?? (AyuRuntimeSettings.snapshot.saveReadDates ? stored.localReadAt : nil)

    var didAddMediaDetails = false
'''
        new_effective = '''    let effectiveReadAt = telegramReadAt ?? (AyuRuntimeSettings.snapshot.saveReadDates ? stored.localReadAt : nil)
    let effectiveContentReadAt = AyuRuntimeSettings.snapshot.saveReadDates ? (stored.localContentReadAt ?? telegramReadAt) : nil

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

    print("[ayu-spy-content-read-dates] voice/round content read timestamps installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
