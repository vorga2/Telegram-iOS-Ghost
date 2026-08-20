#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_THEME_STATE_MIGRATION_v2"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_theme_state_migration.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Sources/SharedAccountContext.swift"
    text = path.read_text(encoding="utf-8")

    if MARK not in text:
        anchor = """        self.accountManager = accountManager
        self.navigateToChatImpl = navigateToChat
"""
        replacement = f"""        self.accountManager = accountManager

        // {MARK}
        // Older Ayu test builds could leave mutually incompatible base-theme,
        // accent, bubble and wallpaper mappings in the shared app container.
        // Clear that legacy state exactly once, then let stock Telegram own every
        // subsequent theme selection and render decision.
        if applicationBindings.isMainApp {{
            let migrationKey = "com.nomadvorga.telegram.ayu.themeStateMigration.v2"
            if !UserDefaults.standard.bool(forKey: migrationKey) {{
                let _ = updatePresentationThemeSettingsInteractively(accountManager: accountManager, {{ current in
                    return PresentationThemeSettings(
                        theme: .builtin(.dayClassic),
                        themePreferredBaseTheme: [:],
                        themeSpecificAccentColors: [:],
                        themeSpecificChatWallpapers: [:],
                        useSystemFont: current.useSystemFont,
                        fontSize: current.fontSize,
                        listsFontSize: current.listsFontSize,
                        chatBubbleSettings: current.chatBubbleSettings,
                        automaticThemeSwitchSetting: AutomaticThemeSwitchSetting(force: false, trigger: .system, theme: .builtin(.night)),
                        largeEmoji: current.largeEmoji,
                        reduceMotion: current.reduceMotion
                    )
                }}).start(completed: {{
                    UserDefaults.standard.set(true, forKey: migrationKey)
                }})
            }}
        }}

        self.navigateToChatImpl = navigateToChat
"""
        text = one(text, anchor, replacement, "theme-state migration")
        path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    for required in (
        MARK,
        'themePreferredBaseTheme: [:]',
        'themeSpecificAccentColors: [:]',
        'themeSpecificChatWallpapers: [:]',
        '.start(completed:',
        'UserDefaults.standard.set(true, forKey: migrationKey)',
    ):
        if required not in verify:
            raise RuntimeError(f"theme-state migration incomplete: {required}")

    print("[ayu-theme-state] one-time legacy state migration installed; stock Telegram theme pipeline preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
