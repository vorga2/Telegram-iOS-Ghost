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
    py_compile.compile(str(requested), doraise=True)
    py_compile.compile(str(correctness), doraise=True)

    subprocess.run([sys.executable, str(requested), str(telegram)], check=True)
    subprocess.run([sys.executable, str(correctness), str(telegram)], check=True)

    runtime = (telegram / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    require('case .trash:\n            return "🗑️"' in runtime, "trash marker is not 🗑️")

    manager = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManager.swift").read_text(encoding="utf-8")
    require("AYU_SPY_HISTORY_MENU_v0_3" in manager, "edit-history query helper missing")
    require("SELECT edited_at, previous_text FROM edit_history" in manager, "edit-history query missing")

    # Edit history must be captured from Telegram's canonical mutation replay so
    # raw updates, getDifference and channel sync all take the same path.
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

    # Live deleted restyle is a single Postbox identity change on the delete event;
    # there are no timers, polling loops or per-frame DB reads.
    stable_refresh = "UInt32(bitPattern: currentMessage.id.id) ^ 0xA5A5A5A5"
    require(manager.count(stable_refresh) >= 2, "one-shot live deleted stable-id refresh missing")
    require("AYU_DELETED_STABLE_REFRESH_v0_3" in manager, "live deleted refresh marker missing")

    menu = (telegram / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift").read_text(encoding="utf-8")
    require('text: "История"' in menu, "History context action missing")
    require("ayuEditHistoryMenuItems" in menu and "ayuSpyEditHistory" in menu, "History nested menu wiring missing")
    history_pos = menu.find('text: "История"')
    read_pos = menu.find('text: "Прочитать"')
    require(history_pos >= 0 and read_pos >= 0 and history_pos < read_pos, "History must be above Read")

    settings = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    require("AYU_GHOST_DROPDOWN_v0_3" in settings, "Ghost dropdown marker missing")
    require('.header("Режим призрака \\(enabledCount)/5", expanded)' in settings, "Ghost 5/5 header missing")
    require("arguments.toggleExpanded" in settings, "Ghost header does not expand/collapse")
    require('(.trash, "🗑️")' in settings, "trash picker still uses eye")

    bubble = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift").read_text(encoding="utf-8")
    require("AYU_STOCK_BUBBLE_ALPHA_v0_3" in bubble, "stock deleted bubble alpha patch missing")
    require("let ayuDeletedVisible" in bubble, "deleted state is not cached per item layout")
    require("let ayuTelegramThemeDeleted = ayuDeletedVisible && ayuDeletedBackgroundColor == nil" in bubble, "Telegram-theme deleted path missing")
    require("backgroundNode.alpha = ayuTelegramThemeDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0" in bubble, "stock bubble is not faded to deleted alpha")
    require("backgroundWallpaperNode.alpha = ayuTelegramThemeDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0" in bubble, "wallpaper bubble is not faded to deleted alpha")

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
