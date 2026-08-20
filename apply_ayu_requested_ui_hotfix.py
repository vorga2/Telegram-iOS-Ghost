#!/usr/bin/env python3
from pathlib import Path
import sys

HISTORY_MARK = "AYU_SPY_HISTORY_MENU_v0_3"
GHOST_MARK = "AYU_GHOST_DROPDOWN_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_requested_ui_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # 1) Deleted marker: .trash is a real trash-can emoji, never the eye marker.
    runtime_path = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    runtime = runtime_path.read_text(encoding="utf-8")
    trash_branch = '        case .trash:\n            return "👀"\n'
    trash_branch_alt = '        case .trash:\n            return "🗑"\n'
    trash_new = '        case .trash:\n            return "🗑️"\n'
    if trash_branch in runtime:
        runtime = runtime.replace(trash_branch, trash_new, 1)
    elif trash_branch_alt in runtime:
        runtime = runtime.replace(trash_branch_alt, trash_new, 1)
    elif trash_new not in runtime:
        raise RuntimeError("trash marker branch missing")
    runtime_path.write_text(runtime, encoding="utf-8")

    # 2) Edit-history query: reuse the existing indexed edit_history table.
    manager_path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    manager = manager_path.read_text(encoding="utf-8")
    if HISTORY_MARK not in manager:
        anchor = "private enum AccountStateManagerOperationContent {\n"
        helper = r'''// AYU_SPY_HISTORY_MENU_v0_3
public struct AyuSpyEditRevision {
    public let editedAt: Int64
    public let previousText: String

    public init(editedAt: Int64, previousText: String) {
        self.editedAt = editedAt
        self.previousText = previousText
    }
}

public func ayuSpyEditHistory(_ messageId: MessageId) -> [AyuSpyEditRevision] {
    guard AyuRuntimeSettings.snapshot.saveEditHistory else {
        return []
    }
    guard let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else {
        return []
    }
    let databasePath = documents
        .appendingPathComponent("Deleted", isDirectory: true)
        .appendingPathComponent("deleted.sqlite")
        .path
    guard FileManager.default.fileExists(atPath: databasePath), let database = Database(databasePath, readOnly: true) else {
        return []
    }

    let peerId = messageId.peerId.toInt64()
    let rows = database.queryRows("SELECT edited_at, previous_text FROM edit_history WHERE peer_id = \(peerId) AND message_namespace = \(messageId.namespace) AND message_id = \(messageId.id) ORDER BY edited_at ASC")
    return rows.compactMap { row -> AyuSpyEditRevision? in
        guard row.count >= 2, let editedRaw = row[0], let editedAt = Int64(editedRaw), let previousText = row[1] else {
            return nil
        }
        return AyuSpyEditRevision(editedAt: editedAt, previousText: previousText)
    }
}

'''
        manager = one(manager, anchor, helper + anchor, "edit history query helper")
    manager_path.write_text(manager, encoding="utf-8")

    # 3) Context menu: History sits immediately above Ayu's explicit Read action.
    menu_path = root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift"
    menu = menu_path.read_text(encoding="utf-8")
    if HISTORY_MARK not in menu:
        helper_anchor = "private struct MessageContextMenuData {\n"
        menu_helper = r'''// AYU_SPY_HISTORY_MENU_v0_3
private func ayuEditHistoryMenuItems(message: EngineRawMessage, revisions: [AyuSpyEditRevision]) -> [ContextMenuItem] {
    var items: [ContextMenuItem] = []
    items.append(.action(ContextMenuActionItem(text: "Назад", icon: { _ in nil }, action: { controller, _ in
        controller?.popItems()
    })))
    items.append(.separator)

    for (index, revision) in revisions.enumerated() {
        let title = index == 0 ? "Исходный текст" : "Версия \(index + 1)"
        items.append(ayuDetailsRow("\(title) · до \(ayuDetailsDate(revision.editedAt))\n\(revision.previousText)"))
    }

    items.append(.separator)
    items.append(ayuDetailsRow("Текущая версия\n\(message.text)"))
    return items
}

'''
        menu = one(menu, helper_anchor, menu_helper + helper_anchor, "history menu helper")

        read_anchor = "        if AyuRuntimeSettings.suppressReadMessages, let ayuMessage = messages.first, ayuMessage.effectivelyIncoming(context.account.peerId) {\n"
        history_action = r'''        // AYU_REQUESTED_UI_HISTORY_v0_3
        if let ayuHistoryMessage = messages.first,
           ayuHistoryMessage.effectivelyIncoming(context.account.peerId),
           AyuRuntimeSettings.snapshot.saveEditHistory {
            let ayuHistory = ayuSpyEditHistory(ayuHistoryMessage.id)
            if !ayuHistory.isEmpty {
                if !actions.isEmpty {
                    actions.append(.separator)
                }
                actions.append(.action(ContextMenuActionItem(text: "История", icon: { _ in nil }, action: { controller, _ in
                    guard let controller else {
                        return
                    }
                    let historyItems = ayuEditHistoryMenuItems(message: ayuHistoryMessage, revisions: ayuHistory)
                    controller.pushItems(items: .single(ContextController.Items(content: .list(historyItems))))
                })))
            }
        }

'''
        menu = one(menu, read_anchor, history_action + read_anchor, "History before Read")
    menu_path.write_text(menu, encoding="utf-8")

    # 4) Ghost settings: 5/5 is a collapsible header.
    settings_path = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    settings = settings_path.read_text(encoding="utf-8")
    settings = settings.replace('(.trash, "👀")', '(.trash, "🗑️")', 1)

    if GHOST_MARK not in settings:
        old_args = '''private final class AyuGhostArguments {\n    let updateBool: (AyuRuntimeOption, Bool) -> Void\n    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void) {\n        self.updateBool = updateBool\n    }\n}\n'''
        new_args = '''private final class AyuGhostArguments {\n    let updateBool: (AyuRuntimeOption, Bool) -> Void\n    var toggleExpanded: (() -> Void)?\n    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void) {\n        self.updateBool = updateBool\n    }\n}\n'''
        settings = one(settings, old_args, new_args, "Ghost arguments")

        settings = one(
            settings,
            "private enum AyuGhostEntry: ItemListNodeEntry {\n    case header\n",
            "private enum AyuGhostEntry: ItemListNodeEntry {\n    // AYU_GHOST_DROPDOWN_v0_3\n    case header(String, Bool)\n",
            "Ghost header case",
        )

        old_header_item = '''        case .header:\n            return ItemListSectionHeaderItem(presentationData: presentationData, text: "РЕЖИМ ПРИЗРАКА", sectionId: self.section)\n'''
        new_header_item = '''        case let .header(title, _):\n            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: title, label: "", sectionId: self.section, style: .blocks, action: { arguments.toggleExpanded?() })\n'''
        settings = one(settings, old_header_item, new_header_item, "Ghost dropdown header item")

        old_entries = r'''private func ayuGhostEntries(_ snapshot: AyuRuntimeSnapshot) -> [AyuGhostEntry] {
    let enabledCount = [snapshot.hideReadMessages, snapshot.hideReadStories, snapshot.hideOnline, snapshot.hideTyping, snapshot.automaticOffline].filter { $0 }.count
    return [
        .header,
        .master("Режим призрака \(enabledCount)/5", snapshot.master),
        .read(snapshot.hideReadMessages),
        .stories(snapshot.hideReadStories),
        .online(snapshot.hideOnline),
        .typing(snapshot.hideTyping),
        .automaticOffline(snapshot.automaticOffline),
        .actionsHeader,
        .readOnActions(snapshot.readOnActions),
        .useScheduled(snapshot.useScheduled),
        .useScheduledInfo
    ]
}
'''
        new_entries = r'''private func ayuGhostEntries(_ snapshot: AyuRuntimeSnapshot, expanded: Bool) -> [AyuGhostEntry] {
    let enabledCount = [snapshot.hideReadMessages, snapshot.hideReadStories, snapshot.hideOnline, snapshot.hideTyping, snapshot.automaticOffline].filter { $0 }.count
    var entries: [AyuGhostEntry] = [
        .header("Режим призрака \(enabledCount)/5", expanded)
    ]
    if expanded {
        entries.append(contentsOf: [
            .master("Включить режим призрака", snapshot.master),
            .read(snapshot.hideReadMessages),
            .stories(snapshot.hideReadStories),
            .online(snapshot.hideOnline),
            .typing(snapshot.hideTyping),
            .automaticOffline(snapshot.automaticOffline),
            .actionsHeader,
            .readOnActions(snapshot.readOnActions),
            .useScheduled(snapshot.useScheduled),
            .useScheduledInfo
        ])
    }
    return entries
}
'''
        settings = one(settings, old_entries, new_entries, "Ghost entries dropdown")

        ghost_start = settings.find("private func ayuGhostSettingsController(context: AccountContext) -> ViewController {")
        ghost_end_candidates = [
            settings.find("private func ayuSpySettingsController(context: AccountContext) -> ViewController {", ghost_start),
            settings.find("func ayuSettingsController(context: AccountContext) -> ViewController {", ghost_start),
        ]
        ghost_end_candidates = [value for value in ghost_end_candidates if value >= 0]
        if ghost_start < 0 or not ghost_end_candidates:
            raise RuntimeError("Ghost controller bounds missing")
        ghost_end = min(ghost_end_candidates)
        ghost = settings[ghost_start:ghost_end]

        ghost = one(
            ghost,
            "    var revisionValue: Int32 = 0\n",
            "    var revisionValue: Int32 = 0\n    var expandedValue = false\n",
            "Ghost expanded state",
        )

        # Generated Ayu settings keep the signal pipeline on one line. Anchor only
        # the stable start of the declaration instead of depending on formatting.
        signal_start = ghost.find("    let signal = combineLatest(")
        if signal_start < 0:
            raise RuntimeError("Ghost signal anchor missing")
        toggle_code = "    arguments.toggleExpanded = {\n        expandedValue.toggle()\n        bump()\n    }\n"
        ghost = ghost[:signal_start] + toggle_code + ghost[signal_start:]

        ghost = one(
            ghost,
            "ayuGhostEntries(AyuRuntimeSettings.snapshot)",
            "ayuGhostEntries(AyuRuntimeSettings.snapshot, expanded: expandedValue)",
            "Ghost expanded entries call",
        )
        settings = settings[:ghost_start] + ghost + settings[ghost_end:]

    settings_path.write_text(settings, encoding="utf-8")

    print("[ayu-requested-ui] 🗑️ marker + edit History menu + collapsible Ghost 5/5 header installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
