#!/usr/bin/env python3
from __future__ import annotations

import os
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

    subprocess.run(
        [sys.executable, str(workspace / "apply_ayu_requested_ui_hotfix.py"), str(telegram)],
        check=True,
    )

    runtime = (telegram / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    require('case .trash:\n            return "🗑️"' in runtime, "trash marker is not 🗑️")

    manager = (telegram / "submodules/TelegramCore/Sources/State/AccountStateManager.swift").read_text(encoding="utf-8")
    require("AYU_SPY_HISTORY_MENU_v0_3" in manager, "edit-history query helper missing")
    require("SELECT edited_at, previous_text FROM edit_history" in manager, "edit-history query missing")

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

    print("=== REQUESTED UI VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== REQUESTED UI VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
