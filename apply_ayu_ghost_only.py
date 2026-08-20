#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import apply_ayu_v03 as base
import apply_ayu_v03_ui_v2 as ui_v2


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply minimal AyuGram Ghost-only patch to Telegram-iOS")
    parser.add_argument("repo", nargs="?", default=".")
    args = parser.parse_args()

    root = Path(args.repo).expanduser().resolve()
    if not (root / "submodules" / "TelegramCore").exists():
        base.die(f"'{root}' is not TelegramMessenger/Telegram-iOS")

    here = Path(__file__).resolve().parent
    state = root / "submodules/TelegramCore/Sources/State"

    # Minimal payload: no deleted-message state, no Spy/history/archive settings.
    base.install_payload(
        here / "payload" / "AyuRuntimeSettingsGhostOnly.swift",
        state / "AyuRuntimeSettings.swift",
        "Ghost-only runtime settings",
    )
    base.install_payload(
        here / "payload" / "AyuGhostLastSeen.swift",
        state / "AyuGhostLastSeen.swift",
        "Ghost last-seen state",
    )
    base.install_payload(
        here / "payload" / "AyuSettingsControllerGhostOnly.swift",
        root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift",
        "Ghost-only Ayu settings controller",
    )

    # Privacy/Ghost hooks only. Deliberately do NOT touch:
    # AccountStateManagementUtils, message item rendering, reply/date/status nodes,
    # deleted retention, archives, Files, Spy/history, view-once or gift/pinned UI.
    base.patch_file(state / "ManagedAccountPresence.swift", base.patch_presence)
    base.patch_file(state / "ManagedLocalInputActivities.swift", base.patch_typing)
    base.patch_file(state / "SynchronizePeerReadState.swift", ui_v2.patch_read_state)
    base.patch_file(state / "ManagedSynchronizeViewStoriesOperations.swift", base.patch_stories)
    base.patch_file(root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift", base.patch_online_pulse)
    base.patch_file(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoSettingsItems.swift", base.patch_native_settings)
    base.patch_file(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoData.swift", base.patch_own_profile_last_seen)

    print("[ayu-ghost-only] DONE")
    print("[ayu-ghost-only] Telegram stock UI/theme retained; Deleted/Spy/History/ViewOnce hooks are absent")


if __name__ == "__main__":
    main()
