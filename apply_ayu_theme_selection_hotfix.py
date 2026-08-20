#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_THEME_VARIANT_SELECTION_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def patch_theme_settings_controller(root: Path) -> None:
    path = root / "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift"
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return

    old_start = '''    selectThemeImpl = { theme in
        guard let presentationTheme = makePresentationTheme(mediaBox: context.sharedContext.accountManager.mediaBox, themeReference: theme) else {
            return
        }
        
        let autoNightModeTriggered = context.sharedContext.currentPresentationData.with { $0 }.autoNightModeTriggered
'''
    new_start = '''    selectThemeImpl = { theme in
        // AYU_THEME_VARIANT_SELECTION_v0_3
        // Resolve a multi-variant cloud theme against the appearance Telegram is
        // already using. This runs only when the user selects a theme: no timers,
        // polling, display-link callbacks or per-frame work are introduced.
        let ayuCurrentPresentationData = context.sharedContext.currentPresentationData.with { $0 }
        let ayuThemeSelectionIsDark = ayuCurrentPresentationData.theme.overallDarkAppearance
        let ayuSelectedBaseTheme: TelegramBaseTheme?
        if case let .cloud(info) = theme {
            ayuSelectedBaseTheme = info.theme.settings?.first(where: { settings in
                if ayuThemeSelectionIsDark {
                    return settings.baseTheme == .night || settings.baseTheme == .tinted
                } else {
                    return settings.baseTheme == .classic || settings.baseTheme == .day
                }
            })?.baseTheme ?? info.theme.settings?.first?.baseTheme
        } else {
            ayuSelectedBaseTheme = nil
        }
        guard let presentationTheme = makePresentationTheme(mediaBox: context.sharedContext.accountManager.mediaBox, themeReference: theme, baseTheme: ayuSelectedBaseTheme) else {
            return
        }
        
        let autoNightModeTriggered = ayuCurrentPresentationData.autoNightModeTriggered
'''
    text = one(text, old_start, new_start, "ThemeSettings selectTheme appearance anchor")

    old_current = '''            if case let .cloud(info) = currentTheme, let settings = info.theme.settings?.first {
                currentThemeBaseIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
            } else {
'''
    new_current = '''            if case let .cloud(info) = currentTheme, let settings = info.theme.settings?.first(where: { settings in
                if ayuThemeSelectionIsDark {
                    return settings.baseTheme == .night || settings.baseTheme == .tinted
                } else {
                    return settings.baseTheme == .classic || settings.baseTheme == .day
                }
            }) ?? info.theme.settings?.first {
                currentThemeBaseIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
            } else {
'''
    text = one(text, old_current, new_current, "ThemeSettings current cloud base anchor")

    old_selected = '''                if let settings = info.theme.settings?.first {
                    baseThemeIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
                    updatedThemeBaseIndex = baseThemeIndex
                }
'''
    new_selected = '''                if let settings = info.theme.settings?.first(where: { settings in
                    if ayuThemeSelectionIsDark {
                        return settings.baseTheme == .night || settings.baseTheme == .tinted
                    } else {
                        return settings.baseTheme == .classic || settings.baseTheme == .day
                    }
                }) ?? info.theme.settings?.first {
                    baseThemeIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
                    updatedThemeBaseIndex = baseThemeIndex
                }
'''
    text = one(text, old_selected, new_selected, "ThemeSettings selected cloud base anchor")

    transaction_anchor = '''            let _ = updatePresentationThemeSettingsInteractively(accountManager: context.sharedContext.accountManager, { current in
                var updatedAutomaticThemeSwitchSetting = current.automaticThemeSwitchSetting
'''
    transaction_new = '''            let _ = updatePresentationThemeSettingsInteractively(accountManager: context.sharedContext.accountManager, { current in
                var updatedThemePreferredBaseTheme = current.themePreferredBaseTheme
                if let ayuSelectedBaseTheme = ayuSelectedBaseTheme {
                    updatedThemePreferredBaseTheme[updatedTheme.index] = ayuSelectedBaseTheme
                }
                var updatedAutomaticThemeSwitchSetting = current.automaticThemeSwitchSetting
'''
    text = one(text, transaction_anchor, transaction_new, "ThemeSettings preferred base persistence anchor")

    return_anchor = '''                return current.withUpdatedTheme(updatedTheme).withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)
'''
    return_new = '''                return current.withUpdatedTheme(updatedTheme).withUpdatedThemePreferredBaseTheme(updatedThemePreferredBaseTheme).withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)
'''
    text = one(text, return_anchor, return_new, "ThemeSettings preferred base return anchor")

    path.write_text(text, encoding="utf-8")


def patch_theme_picker_controller(root: Path) -> None:
    path = root / "submodules/SettingsUI/Sources/ThemePickerController.swift"
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return

    old_start = '''    selectThemeImpl = { baseTheme, theme, preset in
        guard let presentationTheme = makePresentationTheme(mediaBox: context.sharedContext.accountManager.mediaBox, themeReference: theme) else {
            return
        }
        
        let autoNightModeTriggered = context.sharedContext.currentPresentationData.with { $0 }.autoNightModeTriggered
'''
    new_start = '''    selectThemeImpl = { baseTheme, theme, preset in
        // AYU_THEME_VARIANT_SELECTION_v0_3
        // Preserve Telegram's normal theme machinery; only resolve the cloud theme's
        // base variant at the moment of selection so light and dark colors cannot mix.
        let ayuCurrentPresentationData = context.sharedContext.currentPresentationData.with { $0 }
        let ayuThemeSelectionIsDark = ayuCurrentPresentationData.theme.overallDarkAppearance
        let ayuSelectedBaseTheme: TelegramBaseTheme?
        if let baseTheme = baseTheme {
            ayuSelectedBaseTheme = baseTheme
        } else if case let .cloud(info) = theme {
            ayuSelectedBaseTheme = info.theme.settings?.first(where: { settings in
                if ayuThemeSelectionIsDark {
                    return settings.baseTheme == .night || settings.baseTheme == .tinted
                } else {
                    return settings.baseTheme == .classic || settings.baseTheme == .day
                }
            })?.baseTheme ?? info.theme.settings?.first?.baseTheme
        } else {
            ayuSelectedBaseTheme = nil
        }
        guard let presentationTheme = makePresentationTheme(mediaBox: context.sharedContext.accountManager.mediaBox, themeReference: theme, baseTheme: ayuSelectedBaseTheme) else {
            return
        }
        
        let autoNightModeTriggered = ayuCurrentPresentationData.autoNightModeTriggered
'''
    text = one(text, old_start, new_start, "ThemePicker selectTheme appearance anchor")

    old_current = '''            if case let .cloud(info) = currentTheme, let settings = info.theme.settings?.first {
                currentThemeBaseIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
            } else {
'''
    new_current = '''            if case let .cloud(info) = currentTheme, let settings = info.theme.settings?.first(where: { settings in
                if ayuThemeSelectionIsDark {
                    return settings.baseTheme == .night || settings.baseTheme == .tinted
                } else {
                    return settings.baseTheme == .classic || settings.baseTheme == .day
                }
            }) ?? info.theme.settings?.first {
                currentThemeBaseIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
            } else {
'''
    text = one(text, old_current, new_current, "ThemePicker current cloud base anchor")

    old_base = '''                if let baseTheme = baseTheme, let settings = info.theme.settings?.first(where: { $0.baseTheme == baseTheme }) {
                    updatedBaseTheme = baseTheme
                    baseThemeIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
                    updatedThemeBaseIndex = baseThemeIndex
                } else if let settings = info.theme.settings?.first {
'''
    new_base = '''                if let ayuSelectedBaseTheme = ayuSelectedBaseTheme, let settings = info.theme.settings?.first(where: { $0.baseTheme == ayuSelectedBaseTheme }) {
                    updatedBaseTheme = ayuSelectedBaseTheme
                    baseThemeIndex = PresentationThemeReference.builtin(PresentationBuiltinThemeReference(baseTheme: settings.baseTheme)).index
                    updatedThemeBaseIndex = baseThemeIndex
                } else if let settings = info.theme.settings?.first {
'''
    text = one(text, old_base, new_base, "ThemePicker selected cloud base anchor")

    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_theme_selection_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_theme_settings_controller(root)
    patch_theme_picker_controller(root)
    print("[ayu-theme-selection] cloud theme light/dark variant follows current appearance; selection-time only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
