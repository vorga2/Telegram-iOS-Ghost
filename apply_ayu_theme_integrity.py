#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


STATE_MARK = "AYU_THEME_STATE_RECOVERY_v3"
FAMILY_MARK = "AYU_THEME_FAMILY_INTEGRITY_v3"
BASE_MARK = "AYU_MANUAL_THEME_BASE_INTEGRITY_v3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def patch_state(root: Path) -> None:
    path = root / "submodules/TelegramUI/Sources/SharedAccountContext.swift"
    text = path.read_text(encoding="utf-8")
    if STATE_MARK in text:
        return

    anchor = """        self.accountManager = accountManager
        self.navigateToChatImpl = navigateToChat
"""
    replacement = f"""        self.accountManager = accountManager

        // {STATE_MARK}
        // ThemeRepair v1/v2 replaced valid Telegram preferences with an empty
        // palette map and forced the system Auto-Night trigger. Undo only that
        // forced trigger once. Keep the user's selected day/night themes, accent
        // colors, wallpapers, bubbles, fonts and accessibility preferences.
        if applicationBindings.isMainApp {{
            let recoveryKey = "com.nomadvorga.telegram.ayu.themeStateRecovery.v3"
            if !UserDefaults.standard.bool(forKey: recoveryKey) {{
                let _ = updatePresentationThemeSettingsInteractively(accountManager: accountManager, {{ current in
                    var automaticThemeSwitchSetting = current.automaticThemeSwitchSetting
                    automaticThemeSwitchSetting.force = false
                    automaticThemeSwitchSetting.trigger = .explicitNone
                    return PresentationThemeSettings(
                        theme: current.theme,
                        themePreferredBaseTheme: current.themePreferredBaseTheme,
                        themeSpecificAccentColors: current.themeSpecificAccentColors,
                        themeSpecificChatWallpapers: current.themeSpecificChatWallpapers,
                        useSystemFont: current.useSystemFont,
                        fontSize: current.fontSize,
                        listsFontSize: current.listsFontSize,
                        chatBubbleSettings: current.chatBubbleSettings,
                        automaticThemeSwitchSetting: automaticThemeSwitchSetting,
                        largeEmoji: current.largeEmoji,
                        reduceMotion: current.reduceMotion
                    )
                }}).start(completed: {{
                    UserDefaults.standard.set(true, forKey: recoveryKey)
                }})
            }}
        }}

        self.navigateToChatImpl = navigateToChat
"""
    path.write_text(one(text, anchor, replacement, "theme state recovery"), encoding="utf-8")


def patch_family_resolver(root: Path) -> None:
    path = root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift"
    text = path.read_text(encoding="utf-8")
    if FAMILY_MARK in text:
        return

    import_anchor = "import TelegramCore\n\n"
    helper = f'''import TelegramCore

// {FAMILY_MARK}
// Telegram cloud themes may contain classic/day and night/tinted records in any
// order. Never combine the foreground colors of one family with the background
// and native-glass appearance of the other family.
private func ayuCompatibleThemeSettings(_ values: [TelegramThemeSettings]?, baseTheme: TelegramBaseTheme?) -> TelegramThemeSettings? {{
    guard let values, !values.isEmpty else {{
        return nil
    }}
    if let baseTheme {{
        if let exact = values.first(where: {{ $0.baseTheme == baseTheme }}) {{
            return exact
        }}
        let wantsDark = baseTheme == .night || baseTheme == .tinted
        return values.first(where: {{ value in
            wantsDark
                ? (value.baseTheme == .night || value.baseTheme == .tinted)
                : (value.baseTheme == .classic || value.baseTheme == .day)
        }})
    }}
    // The regular non-Auto-Night picker is the light slot. A dark-only theme is
    // still valid and remains dark; a multi-variant theme starts from its light
    // record until Telegram persists an explicit preferred base.
    return values.first(where: {{ $0.baseTheme == .classic || $0.baseTheme == .day }}) ?? values.first
}}

'''
    text = one(text, import_anchor, helper, "theme family helper")

    old_overload = '''public func makePresentationTheme(cloudTheme: TelegramTheme, baseTheme: TelegramBaseTheme? = nil) -> PresentationTheme? {
    let settings: TelegramThemeSettings?
    if let exactSettings = cloudTheme.settings?.first(where: { $0.baseTheme == baseTheme }) {
        settings = exactSettings
    } else if let firstSettings = cloudTheme.settings?.first {
        settings = firstSettings
    } else {
        settings = nil
    }
'''
    new_overload = '''public func makePresentationTheme(cloudTheme: TelegramTheme, baseTheme: TelegramBaseTheme? = nil) -> PresentationTheme? {
    let settings = ayuCompatibleThemeSettings(cloudTheme.settings, baseTheme: baseTheme)
'''
    text = one(text, old_overload, new_overload, "cloud overload resolver")

    old_runtime = '''        case let .cloud(info):
            let settings: TelegramThemeSettings?
            if let exactSettings = info.theme.settings?.first(where: { $0.baseTheme == baseTheme }) {
                settings = exactSettings
            } else if let firstSettings = info.theme.settings?.first {
                settings = firstSettings
            } else {
                settings = nil
            }
            if let settings = settings {
'''
    new_runtime = '''        case let .cloud(info):
            let settings = ayuCompatibleThemeSettings(info.theme.settings, baseTheme: baseTheme)
            if let settings = settings {
'''
    text = one(text, old_runtime, new_runtime, "runtime cloud resolver")
    path.write_text(text, encoding="utf-8")


def patch_manual_base(root: Path) -> None:
    path = root / "submodules/TelegramPresentationData/Sources/PresentationData.swift"
    text = path.read_text(encoding="utf-8")
    if BASE_MARK in text:
        return

    import_anchor = "import PresentationStrings\n\n"
    helper = f'''import PresentationStrings

// {BASE_MARK}
private func ayuManualThemeBase(_ settings: PresentationThemeSettings, reference: PresentationThemeReference) -> TelegramBaseTheme? {{
    if let preferred = settings.themePreferredBaseTheme[reference.index] {{
        return preferred
    }}
    if case let .cloud(info) = reference, let values = info.theme.settings, !values.isEmpty {{
        return values.first(where: {{ $0.baseTheme == .classic || $0.baseTheme == .day }})?.baseTheme ?? values.first?.baseTheme
    }}
    return nil
}}

'''
    text = one(text, import_anchor, helper, "manual base helper")

    old_initial_manual = '''            if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.classic, .day].contains(baseTheme) {
                preferredBaseTheme = baseTheme
            }
'''
    new_initial_manual = '''            preferredBaseTheme = ayuManualThemeBase(themeSettings, reference: effectiveTheme)
'''
    text = one(text, old_initial_manual, new_initial_manual, "initial manual theme base")

    old_live_manual = '''                            if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.classic, .day].contains(baseTheme) {
                                preferredBaseTheme = baseTheme
                            }
'''
    new_live_manual = '''                            preferredBaseTheme = ayuManualThemeBase(themeSettings, reference: effectiveTheme)
'''
    text = one(text, old_live_manual, new_live_manual, "live manual theme base")

    old_wallpaper = '''            let theme = makePresentationTheme(mediaBox: accountManager.mediaBox, themeReference: themeSettings.theme, accentColor: currentColors?.color, bubbleColors: currentColors?.customBubbleColors ?? [], wallpaper: currentColors?.wallpaper, baseColor: currentColors?.baseColor) ?? defaultPresentationTheme
'''
    new_wallpaper = '''            let manualBaseTheme = ayuManualThemeBase(themeSettings, reference: themeSettings.theme)
            let theme = makePresentationTheme(mediaBox: accountManager.mediaBox, themeReference: themeSettings.theme, baseTheme: manualBaseTheme, accentColor: currentColors?.colorFor(baseTheme: manualBaseTheme ?? .day), bubbleColors: currentColors?.customBubbleColors ?? [], wallpaper: currentColors?.wallpaper, baseColor: currentColors?.baseColor) ?? defaultPresentationTheme
'''
    text = one(text, old_wallpaper, new_wallpaper, "manual wallpaper theme base")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_theme_integrity.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_state(root)
    patch_family_resolver(root)
    patch_manual_base(root)

    shared = (root / "submodules/TelegramUI/Sources/SharedAccountContext.swift").read_text(encoding="utf-8")
    make = (root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift").read_text(encoding="utf-8")
    presentation = (root / "submodules/TelegramPresentationData/Sources/PresentationData.swift").read_text(encoding="utf-8")
    for required, value in (
        (STATE_MARK, shared),
        (FAMILY_MARK, make),
        (BASE_MARK, presentation),
        ("automaticThemeSwitchSetting.trigger = .explicitNone", shared),
        ("themeSpecificAccentColors: current.themeSpecificAccentColors", shared),
        ("themeSpecificChatWallpapers: current.themeSpecificChatWallpapers", shared),
        ("let settings = ayuCompatibleThemeSettings(info.theme.settings, baseTheme: baseTheme)", make),
        ("preferredBaseTheme = ayuManualThemeBase(themeSettings, reference: effectiveTheme)", presentation),
    ):
        if required not in value:
            raise RuntimeError(f"theme integrity incomplete: {required}")

    print("[ayu-theme-integrity] recovered state + deterministic light/dark cloud variants; Telegram UI and native glass remain stock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
