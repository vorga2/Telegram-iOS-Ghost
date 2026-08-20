#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent)).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    telegram = runner_temp / "Telegram-iOS"
    require(telegram.exists(), "hotfix verifier did not leave Telegram-iOS checkout")

    requested = workspace / "apply_ayu_requested_ui_hotfix.py"
    correctness = workspace / "apply_ayu_runtime_correctness_hotfix.py"
    polish = workspace / "apply_ayu_ui_polish_hotfix.py"
    retention = workspace / "apply_ayu_group_retention_hotfix.py"
    subtle = workspace / "apply_ayu_deleted_subtle_alpha_hotfix.py"
    for script in (requested, correctness, polish, retention, subtle):
        py_compile.compile(str(script), doraise=True)

    subprocess.run([sys.executable, str(requested), str(telegram)], check=True)
    subprocess.run([sys.executable, str(correctness), str(telegram)], check=True)
    subprocess.run([sys.executable, str(polish), str(telegram)], check=True)
    subprocess.run([sys.executable, str(retention), str(telegram)], check=True)
    subprocess.run([sys.executable, str(subtle), str(telegram)], check=True)

    runtime = (telegram / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    require('case .trash:\n            return "🗑️"' in runtime, "trash marker is not 🗑️")
    require("AYU_DELETED_ASYNC_PERSIST_v0_3" in runtime, "deleted persistence is still synchronous")
    require("deletedPersistenceQueue.async" in runtime, "deleted persistence queue missing")
    require(runtime.count("persistDeletedStateAsync(updated)") >= 3, "deleted-state mutations do not persist asynchronously")

    manager = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManager.swift").read_text(encoding="utf-8")
    require("AYU_SPY_HISTORY_MENU_v0_3" in manager, "edit-history query helper missing")
    require("SELECT edited_at, previous_text FROM edit_history" in manager, "edit-history query missing")

    # Edit history is captured from Telegram's canonical mutation replay so raw
    # updates, getDifference and channel sync all take the same path.
    require("AYU_CANONICAL_EDIT_HISTORY_v0_3" in manager, "canonical edit-history hook missing")
    require("case let .EditMessage(messageId, updatedMessage)" in manager, "canonical EditMessage operation not captured")
    require("currentMessage.flags.contains(.Incoming)" in manager, "edit history is not limited to interlocutor messages")
    require("currentMessage.text != updatedMessage.text" in manager, "metadata-only edits would pollute history")
    require(manager.count("AyuDeletedArchive.shared.captureEditsBeforeReplay(state:") >= 5, "canonical replay coverage is incomplete")

    add_start = manager.find("        func addUpdates(_ updates: Api.Updates) {")
    add_end = manager.find("        func addUpdateGroups(_ groups: [UpdateGroup]) {", add_start)
    require(add_start >= 0 and add_end > add_start, "AccountStateManager addUpdates bounds missing")
    add_updates = manager[add_start:add_end]
    require("ayuRefreshPreservedDeletedMessages(updates)" in add_updates, "raw deleted refresh was lost")
    require("case .updateEditMessage, .updateEditChannelMessage" not in add_updates, "old raw-only edit interception still active")

    # Live deleted restyle is event-driven only: Atomic state first, one Postbox
    # identity mutation next, disk persistence on a background queue.
    stable_refresh = "UInt32(bitPattern: currentMessage.id.id) ^ 0xA5A5A5A5"
    require(manager.count(stable_refresh) >= 2, "one-shot live deleted stable-id refresh missing")
    require("AYU_DELETED_STABLE_REFRESH_v0_3" in manager, "live deleted refresh marker missing")
    require("AYU_DELETED_LOW_LATENCY_v0_3" in manager, "low-latency raw delete path missing")

    # Startup/reconnect differences and channel available-min cleanup must not
    # remove messages already retained by Ayu. The pinned Telegram source has one
    # canonical replay switch, so verify the two delete cases semantically instead
    # of assuming duplicated replay blocks.
    state_utils = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift").read_text(encoding="utf-8")
    require(state_utils.count("AYU_DELETED_CANONICAL_RETENTION_v0_3") >= 2, "canonical deleted retention is incomplete")
    require(state_utils.count("AYU_DELETED_RANGE_RETENTION_v0_3") >= 1, "channel min-range retention is incomplete")
    require("ayuEffectiveIds = ids.filter { !AyuRuntimeSettings.isDeleted($0) }" in state_utils, "direct canonical deletes can still remove retained messages")
    require("transaction.messageIdsForGlobalIds(ids).filter { AyuRuntimeSettings.isDeleted($0) }" in state_utils, "global canonical deletes can still remove retained messages")
    require("transaction.addMessages(ayuPreservedMessages, location: .Random)" in state_utils, "channel range cleanup does not restore retained messages")

    menu = (telegram / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift").read_text(encoding="utf-8")
    require('text: "История"' in menu, "History context action missing")
    require("AYU_HISTORY_SCROLL_v0_3" in menu, "scrollable History content missing")
    require("AyuEditHistoryContextContent" in menu and "ASScrollNode" in menu, "History is not scrollable")
    require('UIImage(bundleImageName: "Chat/Context Menu/Copy")' in menu, "History icon missing")
    require('UIImage(bundleImageName: "Chat/Context Menu/Back")' in menu, "History Back icon missing")
    require("content: .custom(historyContent)" in menu, "History still uses an unbounded normal context list")
    history_pos = menu.find('text: "История"')
    read_pos = menu.find('text: "Прочитать"')
    require(history_pos >= 0 and read_pos >= 0 and history_pos < read_pos, "History must be above Read")
    require("AYU_CUSTOM_ACTION_SECTION_v0_3" in menu, "Ayu custom action section marker missing")
    require(menu.count("if !ayuCustomActionsStarted {") >= 4, "Ayu actions are not grouped into one section")

    settings = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    require("AYU_GHOST_EXPANDABLE_SWITCH_v0_3" in settings, "Ghost expandable switch missing")
    require("ItemListExpandableSwitchItem(" in settings, "Ghost 5/5 header is not an expandable switch")
    require('.header("Режим призрака \\(enabledCount)/5", expanded)' in settings, "Ghost 5/5 header missing")
    require('ItemListExpandableSwitchItem.SubItem(id: AnyHashable("read")' in settings, "Ghost subitems missing")
    require('.actionsHeader,\n        .readOnActions(snapshot.readOnActions),\n        .useScheduled(snapshot.useScheduled)' in settings, "Actions are not outside the Ghost dropdown")
    require('.master("Включить режим призрака", snapshot.master)' not in settings, "old separate Ghost master row is still emitted")
    require("Сообщения отправляются без краткого выхода в онлайн." in settings, "scheduled-send explanation missing")
    require('(.trash, "🗑️")' in settings, "trash picker still uses eye")

    enqueue = (telegram / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift").read_text(encoding="utf-8")
    require("AYU_GHOST_SCHEDULED_NO_PULSE_v0_3" in enqueue, "useScheduled still performs the online pulse")
    require("snapshot.master && AyuRuntimeSettings.snapshot.useScheduled" in enqueue, "scheduled Ghost send pulse guard missing")

    background = (telegram / "submodules/ChatMessageBackground/Sources/ChatMessageBackground.swift").read_text(encoding="utf-8")
    require("AYU_DELETED_BAKED_ALPHA_v0_3" in background, "cached deleted bubble alpha helper missing")
    require("ayuAlphaImageCache" in background and "ayuCustomImageAlpha" in background, "deleted bubble alpha is not cached")

    bubble = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift").read_text(encoding="utf-8")
    require("let ayuDeletedVisible = AyuRuntimeSettings.isDeleted(item.message.id)" in bubble, "deleted styling is still viewer-dependent")
    require("!AyuRuntimeSettings.isInDeletedViewer(item.message.id)" not in bubble, "deleted viewer still disables background styling")
    require("AYU_DELETED_DARK_THEME_BACKDROP_v0_3" in bubble, "dark-theme Telegram bubble fallback missing")
    require("AYU_DELETED_SUBTLE_THEME_ALPHA_v0_3" in bubble, "subtle Telegram-theme deleted alpha missing")
    require("let ayuDeletedAlpha = CGFloat(AyuRuntimeSettings.deletedMessageAlpha)" in bubble, "deleted alpha value missing")
    require("let ayuTelegramDeletedAlpha = min(ayuDeletedAlpha, CGFloat(0.35))" in bubble, "Telegram-theme background is not capped at 0.35")
    require("backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible && !ayuTelegramThemeDeleted ? ayuDeletedAlpha : nil" in bubble, "Telegram-theme image path still bakes alpha before layer compositing")
    require("if strongSelf.backgroundNode.hasImage" in bubble, "active Telegram bubble source is not detected")
    require("strongSelf.backgroundNode.alpha = ayuTelegramDeletedAlpha" in bubble, "stock image bubble is not faded at the final layer")
    require("strongSelf.backgroundWallpaperNode.alpha = ayuTelegramDeletedAlpha" in bubble, "stock wallpaper bubble is not faded at the final layer")
    require("backgroundWallpaperNode.alpha = ayuDeletedVisible ? 0.0 : 1.0" not in bubble, "dark-theme Telegram bubble can still be hidden completely")
    require("ayuDeletedWholeItem" not in bubble, "whole bubble item alpha leaked back into bubble renderer")

    deleted_viewer = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuDeletedMessagesController.swift").read_text(encoding="utf-8")
    require("beginDeletedViewer" not in deleted_viewer and "endDeletedViewer" not in deleted_viewer, "deleted viewer still leaks full-opacity state into normal chat")

    item = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift").read_text(encoding="utf-8")
    require("ayuDeletedWholeItem" not in item, "whole message item is still faded")
    require("node.alpha = 1.0" in item and "nodeValue.alpha = 1.0" in item, "message content opacity is not stock")

    print("=== REQUESTED UI VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== REQUESTED UI VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
