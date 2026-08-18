#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path


def run(*args: str, cwd: Path | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=str(cwd) if cwd else None, check=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent)).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    telegram = runner_temp / "Telegram-iOS"

    patchers = (
        "apply_ayu_v03.py",
        "apply_ayu_v03_fixed.py",
        "apply_ayu_v03_crashfix.py",
        "apply_ayu_v03_ui_v2.py",
        "apply_ayu_profile_cache.py",
        "apply_ayu_view_once.py",
        "apply_ayu_view_once_durable.py",
        "apply_ayu_view_once_burn.py",
        "apply_ayu_stock_ui_guard.py",
        "apply_ayu_deleted_background.py",
        "apply_ayu_deleted_realtime.py",
        "apply_ayu_manual_read_fix.py",
        "apply_ayu_send_read.py",
        "apply_ayu_manual_read_pulse.py",
    )

    print("=== Python syntax ===", flush=True)
    for name in patchers:
        py_compile.compile(str(workspace / name), doraise=True)
        print(f"OK: {name}")

    ref = (workspace / "telegram-ref.txt").read_text(encoding="utf-8").strip()
    require(bool(ref), "telegram-ref.txt is empty")

    print("=== Checkout pinned Telegram source ===", flush=True)
    shutil.rmtree(telegram, ignore_errors=True)
    run("git", "init", str(telegram))
    run("git", "remote", "add", "origin", "https://github.com/TelegramMessenger/Telegram-iOS.git", cwd=telegram)
    run("git", "fetch", "--depth", "1", "origin", ref, cwd=telegram)
    run("git", "checkout", "--detach", "FETCH_HEAD", cwd=telegram)
    actual_ref = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=telegram, text=True).strip()
    require(actual_ref == ref, f"Pinned Telegram ref mismatch: {actual_ref} != {ref}")

    print("=== Apply final build patch chain ===", flush=True)
    for name in (
        "apply_ayu_v03_ui_v2.py",
        "apply_ayu_profile_cache.py",
        "apply_ayu_view_once.py",
        "apply_ayu_view_once_durable.py",
        "apply_ayu_view_once_burn.py",
        "apply_ayu_stock_ui_guard.py",
        "apply_ayu_deleted_background.py",
        "apply_ayu_deleted_realtime.py",
        "apply_ayu_manual_read_fix.py",
        "apply_ayu_send_read.py",
        "apply_ayu_manual_read_pulse.py",
    ):
        run(sys.executable, str(workspace / name), str(telegram))

    peer_info_root = telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources"

    print("=== Verify settings/runtime ===", flush=True)
    settings = (telegram / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift").read_text(encoding="utf-8")
    require(settings.count('text: "AyuGram"') == 1, "AyuGram settings row missing or duplicated")
    settings_controller = (peer_info_root / "AyuSettingsController.swift").read_text(encoding="utf-8")
    require('title: "Цвет фона удалённых"' in settings_controller, "deleted background color setting title is wrong")
    require("Онлайн на 0,2 с при отправке" not in settings_controller, "0.2 s pulse toggle must not be visible")
    require("ActionSheetController" in settings_controller, "native deleted style/color selectors missing")

    runtime = (telegram / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    require("public static let deletedMessageAlpha: Float = 0.5" in runtime, "deleted bubble alpha is not 0.5")
    require("manualBurnMessages" in runtime, "view-once Burn allowance missing")
    require("shouldPreserveViewOnce(message:" in runtime, "view-once preservation predicate missing")

    print("=== Verify read/send semantics ===", flush=True)
    read_state = (telegram / "submodules/TelegramCore/Sources/State/SynchronizePeerReadState.swift").read_text(encoding="utf-8")
    require("transaction.confirmSynchronizedIncomingReadState(peerId)" in read_state, "transaction-safe Ghost read suppression missing")
    require("AYU_MANUAL_READ_FIX_v0_3" in read_state, "manual Read push-only allowance fix missing")
    dangerous = "if AyuRuntimeSettings.suppressReadMessages {\n        return .single(readState)"
    require(dangerous not in read_state, "old recursive read shortcut returned")

    context_menu = (telegram / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift").read_text(encoding="utf-8")
    require('text: "Прочитать"' in context_menu, "manual Read action missing")
    require("ayuGhostOnlinePulse(account: context.account)" in context_menu, "manual Read 0.2 s pulse missing")
    require('text: "Сжечь"' in context_menu, "view-once Burn action missing")

    enqueue = (telegram / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift").read_text(encoding="utf-8")
    require("public func ayuGhostOnlinePulse(account: Account)" in enqueue, "shared Ghost pulse helper missing")
    require("AYU_SEND_READ_v0_3" in enqueue, "read-current-chat-on-send hook missing")
    require("ayuReadPeerOnSend(account: account, peerId: peerId)" in enqueue, "send does not read current chat")

    print("=== Verify view-once durable preservation ===", flush=True)
    consume = (telegram / "submodules/TelegramCore/Sources/TelegramEngine/Messages/MarkMessageContentAsConsumedInteractively.swift").read_text(encoding="utf-8")
    require("AYU_VIEW_ONCE_DURABLE_v0_3" in consume, "durable view-once patch missing")
    require("ayuRestoreDurableViewOnceMedia" in consume, "durable view-once restore missing")
    require("/ayu-view-once" in consume, "durable storage directory missing")
    require("ayuRemoveDurableViewOnceMedia" in consume, "Burn does not remove durable copy")

    print("=== Verify deleted-message path ===", flush=True)
    state_utils = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift").read_text(encoding="utf-8")
    require("AyuRuntimeSettings.markDeletedGlobalIds" in state_utils, "global deleted retention missing")
    require("AyuRuntimeSettings.markDeletedMessageIds" in state_utils, "channel deleted retention missing")

    state_manager = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManager.swift").read_text(encoding="utf-8")
    require("AYU_IOS_DELETED_REALTIME_v0_3" in state_manager, "real-time deleted refresh missing")
    require("transaction.updateMessage" in state_manager, "real-time deleted Postbox invalidation missing")

    background = (telegram / "submodules/ChatMessageBackground/Sources/ChatMessageBackground.swift").read_text(encoding="utf-8")
    require("ayuCustomFillColor" in background, "deleted bubble custom fill missing")
    require("ayuFillImageCache" in background, "deleted bubble image cache missing")

    bubble = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift").read_text(encoding="utf-8")
    require("ayuDeletedBackgroundColor" in bubble, "deleted bubble tint hook missing")
    require("withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))" in bubble, "deleted bubble background is not alpha 0.5")

    message_item = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift").read_text(encoding="utf-8")
    require("stock message-item renderer preserved" in message_item, "stock message-item guard missing")
    require("AyuRuntimeSettings.deletedMessageAlpha" not in message_item, "whole-message deleted alpha still present")

    status_node = (telegram / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/ChatMessageDateAndStatusNode.swift").read_text(encoding="utf-8")
    require("stock date/status renderer is intentionally preserved" in status_node, "stock date/status guard missing")

    print("=== Verify stock reply/pinned/gifts ===", flush=True)
    for relative in (
        "submodules/TelegramUI/Components/Chat/ChatMessageReplyInfoNode/Sources/ChatMessageReplyInfoNode.swift",
        "submodules/TelegramUI/Sources/ChatPinnedMessageTitlePanelNode.swift",
        "submodules/TelegramUI/Components/PeerInfo/PeerInfoVisualMediaPaneNode/Sources/PeerInfoGiftsPaneNode.swift",
    ):
        actual = (telegram / relative).read_bytes()
        expected = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=telegram)
        require(actual == expected, f"stock UI regression guard failed: {relative}")

    print("=== Verify profile last-known cache ===", flush=True)
    profile = (peer_info_root / "PeerInfoProfileItems.swift").read_text(encoding="utf-8")
    for needle in (
        "AYU_IOS_PROFILE_CACHE_v0_3",
        "let ayuServerPhone",
        "let ayuServerUsername",
        "let ayuDisplayPhone = ayuServerPhone ?? ayuCachedProfile.phone",
        "let ayuDisplayUsername = ayuServerUsername ?? ayuCachedProfile.username",
        "if let phone = ayuDisplayPhone {",
        "if let mainUsername = ayuDisplayUsername {",
        "ayuCachedProfile.note",
    ):
        require(needle in profile, f"profile cache hook missing: {needle}")

    require((peer_info_root / "AyuProfileFieldCache.swift").exists(), "AyuProfileFieldCache.swift missing")
    require((peer_info_root / "AyuDeletedMessagesController.swift").exists(), "AyuDeletedMessagesController.swift missing")
    require((telegram / "submodules/TelegramCore/Sources/State/AyuGhostLastSeen.swift").exists(), "AyuGhostLastSeen.swift missing")

    print("=== VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
