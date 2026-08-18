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
        "apply_ayu_behavior_hotfix.py",
        "apply_ayu_deleted_archive.py",
        "apply_ayu_deleted_visual_hotfix.py",
        "apply_ayu_presence_toggle_hotfix.py",
    )
    for name in patchers:
        py_compile.compile(str(workspace / name), doraise=True)
        run(sys.executable, str(workspace / name), str(telegram))

    enqueue = (telegram / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift").read_text(encoding="utf-8")
    require("AYU_BEHAVIOR_HOTFIX_v0_3" in enqueue, "manual Read behavior hotfix missing")
    require("ayuReadMessageThroughGhost" in enqueue, "manual Read direct max-index helper missing")
    require("AYU_GHOST_PRESENCE_TOGGLE_v0_3" in enqueue, "immediate Ghost presence helper missing")
    require("ayuApplyGhostPresence" in enqueue, "Ghost presence request helper missing")

    menu = (telegram / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift").read_text(encoding="utf-8")
    require("ayuReadMessageThroughGhost(account: context.account" in menu, "manual Read action does not use direct helper")
    require("ayuBurnViewOnceRemotely(account: context.account" in menu, "Burn is not remote-only")
    require("ayuGhostOnlinePulse(account: context.account)" in menu, "Read/Burn online pulse missing")

    consume = (telegram / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift").read_text(encoding="utf-8")
    require("public func ayuBurnViewOnceRemotely" in consume, "remote Burn helper missing")
    require("if AyuRuntimeSettings.shouldPreserveViewOnce(message: message)" in consume, "remote consume does not preserve local view-once")

    manager = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManager.swift").read_text(encoding="utf-8")
    require("LocalMessageTags(rawValue: 1 << 30)" in manager, "real-time deleted invalidation tag missing")
    require("AYU_DELETED_ARCHIVE_v0_3" in manager, "deleted archive hook missing")
    require('documents.appendingPathComponent("AyuGram"' in manager, "Documents/AyuGram archive root missing")
    require('appendingPathComponent("Downloads"' not in manager, "obsolete Documents/Downloads archive layer returned")
    require("Saved attachments" in manager, "saved attachments folder missing")
    require("deleted.sqlite" in manager, "deleted SQLite database missing")
    require("CREATE TABLE IF NOT EXISTS deleted_messages" in manager, "deleted-message database schema missing")
    require("CREATE TABLE IF NOT EXISTS attachments" in manager, "attachment database schema missing")
    require("resourceData(attachment.resource)" in manager and "take(1)" in manager, "attachment archival must be one-shot, not a long-lived watcher")

    runtime = (telegram / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    require("case telegram = 8" in runtime, "Telegram-theme deleted background option missing")
    require("AyuDeletedMarkerColor.telegram.rawValue" in runtime, "Telegram theme is not the deleted-background default")

    settings = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
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
