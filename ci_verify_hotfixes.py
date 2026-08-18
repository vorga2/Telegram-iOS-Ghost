#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path


def run(*args: str) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, check=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent)).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    telegram = runner_temp / "Telegram-iOS"
    require(telegram.exists(), "base verifier did not leave Telegram-iOS checkout")

    patchers = (
        "apply_ayu_behavior_anchor_compat.py",
        "apply_ayu_behavior_hotfix.py",
        "apply_ayu_deleted_archive.py",
        "apply_ayu_files_visibility.py",
        "apply_ayu_deleted_visual_hotfix.py",
        "apply_ayu_presence_toggle_hotfix.py",
        "apply_ayu_settings_categories.py",
        "apply_ayu_spy_settings.py",
        "apply_ayu_spy_edit_history.py",
        "apply_ayu_spy_read_dates.py",
        "apply_ayu_spy_details.py",
    )
    for name in patchers:
        py_compile.compile(str(workspace / name), doraise=True)
        run(sys.executable, str(workspace / name), str(telegram))

    enqueue = (telegram / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift").read_text(encoding="utf-8")
    require("AYU_BEHAVIOR_HOTFIX_v0_3" in enqueue, "manual Read behavior hotfix missing")
    require("ayuReadMessageThroughGhost" in enqueue, "manual Read direct max-index helper missing")
    require("AYU_GHOST_PRESENCE_TOGGLE_v0_3" in enqueue, "immediate Ghost presence helper missing")
    require("ayuApplyGhostPresence" in enqueue, "Ghost presence request helper missing")
    require("snapshot.master, AyuRuntimeSettings.snapshot.readOnActions" in enqueue, "send read-on-actions guard missing")

    menu = (telegram / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift").read_text(encoding="utf-8")
    require("ayuReadMessageThroughGhost(account: context.account" in menu, "manual Read action does not use direct helper")
    require("ayuBurnViewOnceRemotely(account: context.account" in menu, "Burn is not remote-only")
    require("ayuGhostOnlinePulse(account: context.account)" in menu, "Read/Burn online pulse missing")
    require("AYU_SPY_DETAILS_v0_3" in menu, "Spy Details context menu missing")
    require('text: "Детали"' in menu, "Details action missing")
    require('text: "Назад"' in menu and "controller?.popItems()" in menu, "nested Details Back action missing")
    require("controller.pushItems" in menu, "Details must use nested context menu")

    consume = (telegram / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift").read_text(encoding="utf-8")
    require("public func ayuBurnViewOnceRemotely" in consume, "remote Burn helper missing")
    require("if AyuRuntimeSettings.shouldPreserveViewOnce(message: message)" in consume, "remote consume does not preserve local view-once")
    require("snapshot.master && !AyuRuntimeSettings.snapshot.readOnActions" in consume, "media read-on-actions guard missing")

    manager = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManager.swift").read_text(encoding="utf-8")
    require("LocalMessageTags(rawValue: 1 << 30)" in manager, "real-time deleted invalidation tag missing")
    require("AYU_DELETED_ARCHIVE_v0_3" in manager, "deleted archive hook missing")
    require("AYU_SPY_EDIT_HISTORY_v0_3" in manager, "Spy edit-history hook missing")
    require("AYU_SPY_DETAILS_v0_3" in manager, "Spy stored Details helper missing")
    require("ayuSpyStoredMessageDetails" in manager, "Spy DB Details lookup missing")
    require("CREATE TABLE IF NOT EXISTS edit_history" in manager, "Spy edit-history table missing")
    require("edit_history_message_idx" in manager, "Spy edit-history index missing")
    require("AyuRuntimeSettings.snapshot.saveEditHistory" in manager, "Spy edit-history toggle not enforced")
    require("case .updateEditMessage, .updateEditChannelMessage" in manager, "remote edit updates are not intercepted")
    require("transaction.getMessage(id)" in manager and "enqueueEdit(message: currentMessage)" in manager, "previous revision is not captured before replacement")
    require("self.ayuRefreshPreservedDeletedMessages(updates)" in manager, "edit-history integration dropped deleted realtime hook")
    require("        let root = documents\n" in manager, "archive must use exposed Documents root")
    require('documents.appendingPathComponent("AyuGram"' not in manager, "nested AyuGram/AyuGram archive layer returned")
    require('appendingPathComponent("Downloads"' not in manager, "obsolete Documents/Downloads archive layer returned")
    require("Saved attachments" in manager, "saved attachments folder missing")
    require("deleted.sqlite" in manager, "deleted SQLite database missing")
    require("CREATE TABLE IF NOT EXISTS deleted_messages" in manager, "deleted-message database schema missing")
    require("CREATE TABLE IF NOT EXISTS attachments" in manager, "attachment database schema missing")
    require("resourceData(attachment.resource)" in manager and "take(1)" in manager, "attachment archival must be one-shot, not a long-lived watcher")

    state_utils = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift").read_text(encoding="utf-8")
    require("AYU_SPY_READ_DATES_v0_3" in state_utils, "Spy read-date hook missing")
    require("CREATE TABLE IF NOT EXISTS read_receipts" in state_utils, "Spy read-date table missing")
    require("read_receipts_lookup_idx" in state_utils, "Spy read-date lookup index missing")
    require("AyuRuntimeSettings.snapshot.saveReadDates" in state_utils, "Spy read-date toggle not enforced")
    require("case let .updateReadHistoryOutbox" in state_utils, "outgoing read update hook missing")
    require("peerId.namespace != Namespaces.Peer.CloudChannel" in state_utils, "channels are not excluded from local read dates")
    require("INSERT OR IGNORE INTO read_receipts" in state_utils, "local read max-boundary persistence missing")
    require('appendingPathComponent("AyuGram"' not in state_utils, "read-date DB must use exposed Documents root")

    database = (telegram / "submodules/Postbox/Sources/Database.swift").read_text(encoding="utf-8")
    require("AYU_SPY_QUERY_ROWS_v0_3" in database and "public func queryRows" in database, "Ayu SQLite query helper missing")

    plist = (telegram / "Telegram/Telegram-iOS/InfoBazel.plist").read_text(encoding="utf-8")
    require("<string>AyuGram</string>" in plist, "AyuGram Files folder/display name missing")
    require("<key>UIFileSharingEnabled</key>\n\t<true/>" in plist, "UIFileSharingEnabled is not enabled")
    require("<key>LSSupportsOpeningDocumentsInPlace</key>\n\t<true/>" in plist, "open-in-place Files support is not enabled")

    runtime = (telegram / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    require("case telegram = 8" in runtime, "Telegram-theme deleted background option missing")
    require("AyuDeletedMarkerColor.telegram.rawValue" in runtime, "Telegram theme is not the deleted-background default")
    require("case readOnActions = 9" in runtime, "read-on-actions option missing")
    require("case useScheduled = 10" in runtime, "scheduled option missing")
    require("case saveEditHistory = 11" in runtime, "Spy edit-history option missing")
    require("case saveReadDates = 12" in runtime, "Spy read-date option missing")
    require("readOnActions: storedValue(.readOnActions" in runtime, "read-on-actions default persistence missing")
    require("saveEditHistory: storedValue(.saveEditHistory" in runtime, "Spy edit-history persistence missing")
    require("saveReadDates: storedValue(.saveReadDates" in runtime, "Spy read-date persistence missing")

    settings = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    require('title: .text("Настройки AyuGram")' in settings, "AyuGram settings title missing")
    require('text: "КАТЕГОРИИ"' in settings, "categories header missing")
    require('title: "Режим Призрака"' in settings, "Ghost category missing")
    require('title: "Кастомизация"' in settings, "Customization category missing")
    require('title: "Шпион"' in settings, "Spy category missing")
    require('text: "РЕЖИМ ШПИОНА"' in settings, "Spy section header missing")
    require('title: "Сохранять удалённые сообщения"' in settings, "Spy deleted toggle missing")
    require('title: "Сохранять историю правок"' in settings, "Spy edit-history toggle missing")
    require('title: "Сохранять дату прочтения"' in settings, "Spy read-date toggle missing")
    require("Локально сохраняет данные о чтении сообщений" in settings, "Spy read-date description missing")
    require('"Режим призрака \\(enabledCount)/5"' in settings, "Ghost 5/5 counter missing")
    require('title: "Читать при действиях"' in settings, "read-on-actions toggle missing")
    require('title: "Использовать отложку"' in settings, "scheduled toggle missing")
    require("Зажмите любую опцию" not in settings, "pin-option description must not exist")
    require("Отправлять без звука" not in settings, "silent-send setting must not exist")
    require('(.telegram, "Тема Telegram")' in settings, "Telegram-theme choice missing from settings")
    require("ayuApplyGhostPresence(account: context.account)" in settings, "Ghost toggle does not apply presence immediately")

    timestamp = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/StringForMessageTimestampStatus.swift").read_text(encoding="utf-8")
    require("AyuRuntimeSettings.decorateTimestamp" in timestamp, "deleted marker/icon path missing")

    bubble = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift").read_text(encoding="utf-8")
    require("ayuUsesTelegramTheme" in bubble, "Telegram-theme deleted bubble path missing")

    print("=== HOTFIX VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== HOTFIX VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
