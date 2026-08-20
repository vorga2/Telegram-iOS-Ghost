#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

STATE_MARK = "AYU_THEME_STATE_REPAIR_v1"
CLOUD_MARK = "AYU_CLOUD_THEME_FAMILY_FALLBACK_v2"
TRAIT_MARK = "AYU_IOS27_SCENE_TRAIT_REPAIR_v2"
PREFERRED_NIGHT_MARK = "AYU_SPLIT_DAY_NIGHT_THEME_SELECTION_v3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_theme_repair.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # 1) Cloud/custom themes can ship classic+day and night+tinted variants.
    # Stock code asks for one exact baseTheme and otherwise falls back to the first
    # settings entry. If the requested dark base is .night but the theme only ships
    # .tinted, the first entry can be the light variant. Pick a compatible luminance
    # family before falling back to the first setting.
    make_path = root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift"
    make = make_path.read_text(encoding="utf-8")
    if CLOUD_MARK not in make:
        import_anchor = "import TelegramCore\n\n"
        helper = f'''import TelegramCore\n\n// {CLOUD_MARK}\nprivate func ayuCompatibleCloudThemeSettings(_ values: [TelegramThemeSettings]?, baseTheme: TelegramBaseTheme?) -> TelegramThemeSettings? {{\n    guard let values, !values.isEmpty else {{\n        return nil\n    }}\n    guard let baseTheme else {{\n        // PresentationData passes nil for the normal (non Auto-Night) path when\n        // no preferred variant has been persisted. That path is light, so never\n        // let an arbitrarily ordered dark record provide its foreground colors.\n        return values.first(where: {{ $0.baseTheme == .classic || $0.baseTheme == .day }}) ?? values.first\n    }}\n    if let exact = values.first(where: {{ $0.baseTheme == baseTheme }}) {{\n        return exact\n    }}\n    let wantsDark = baseTheme == .night || baseTheme == .tinted\n    if let compatible = values.first(where: {{ value in\n        if wantsDark {{\n            return value.baseTheme == .night || value.baseTheme == .tinted\n        }} else {{\n            return value.baseTheme == .classic || value.baseTheme == .day\n        }}\n    }}) {{\n        return compatible\n    }}\n    // Never apply a palette from the opposite luminance family.\n    return nil\n}}\n\n'''
        make = one(make, import_anchor, helper, "cloud theme compatibility helper")

        old_cloud = '''public func makePresentationTheme(cloudTheme: TelegramTheme, baseTheme: TelegramBaseTheme? = nil) -> PresentationTheme? {\n    let settings: TelegramThemeSettings?\n    if let exactSettings = cloudTheme.settings?.first(where: { $0.baseTheme == baseTheme }) {\n        settings = exactSettings\n    } else if let firstSettings = cloudTheme.settings?.first {\n        settings = firstSettings\n    } else {\n        settings = nil\n    }\n'''
        new_cloud = '''public func makePresentationTheme(cloudTheme: TelegramTheme, baseTheme: TelegramBaseTheme? = nil) -> PresentationTheme? {\n    let settings = ayuCompatibleCloudThemeSettings(cloudTheme.settings, baseTheme: baseTheme)\n'''
        make = one(make, old_cloud, new_cloud, "cloud theme overload family fallback")

        old_case = '''        case let .cloud(info):\n            let settings: TelegramThemeSettings?\n            if let exactSettings = info.theme.settings?.first(where: { $0.baseTheme == baseTheme }) {\n                settings = exactSettings\n            } else if let firstSettings = info.theme.settings?.first {\n                settings = firstSettings\n            } else {\n                settings = nil\n            }\n            if let settings = settings {\n'''
        new_case = '''        case let .cloud(info):\n            let settings = ayuCompatibleCloudThemeSettings(info.theme.settings, baseTheme: baseTheme)\n            if let settings = settings {\n'''
        make = one(make, old_case, new_case, "runtime cloud theme family fallback")
        make_path.write_text(make, encoding="utf-8")

    # 2) Repair only persisted presentation-theme state once. Previous Ayu builds used
    # the same bundle id, so installing a clean binary does not clear theme settings.
    # Preserve font/bubble/accessibility preferences, but clear theme/base/accent/
    # wallpaper mappings and restore Telegram's Day Classic + Night auto target.
    shared_path = root / "submodules/TelegramUI/Sources/SharedAccountContext.swift"
    shared = shared_path.read_text(encoding="utf-8")
    if STATE_MARK not in shared:
        anchor = '''        self.accountManager = accountManager\n        self.navigateToChatImpl = navigateToChat\n'''
        replacement = f'''        self.accountManager = accountManager\n\n        // {STATE_MARK}\n        if applicationBindings.isMainApp {{\n            let repairKey = "com.nomadvorga.telegram.ayu.themeRepair.v1"\n            if !UserDefaults.standard.bool(forKey: repairKey) {{\n                UserDefaults.standard.set(true, forKey: repairKey)\n                let _ = updatePresentationThemeSettingsInteractively(accountManager: accountManager, {{ current in\n                    return PresentationThemeSettings(\n                        theme: .builtin(.dayClassic),\n                        themePreferredBaseTheme: [:],\n                        themeSpecificAccentColors: [:],\n                        themeSpecificChatWallpapers: [:],\n                        useSystemFont: current.useSystemFont,\n                        fontSize: current.fontSize,\n                        listsFontSize: current.listsFontSize,\n                        chatBubbleSettings: current.chatBubbleSettings,\n                        automaticThemeSwitchSetting: AutomaticThemeSwitchSetting(force: false, trigger: .system, theme: .builtin(.night)),\n                        largeEmoji: current.largeEmoji,\n                        reduceMotion: current.reduceMotion\n                    )\n                }}).start()\n            }}\n        }}\n\n        self.navigateToChatImpl = navigateToChat\n'''
        shared = one(shared, anchor, replacement, "one-time theme state repair")
        shared_path.write_text(shared, encoding="utf-8")

    # 3) Publish the real scene appearance for Auto-Night without overriding UIKit.
    # Native iOS 27 Liquid Glass must remain owned by the system window hierarchy.
    window_path = root / "submodules/Display/Source/NativeWindowHostView.swift"
    window = window_path.read_text(encoding="utf-8")
    if TRAIT_MARK not in window:
        old = '''    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {\n        if #available(iOS 12.0, *) {\n            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: self.traitCollection.userInterfaceStyle))\n        }\n    }\n'''
        new = f'''    // {TRAIT_MARK}\n    @available(iOS 13.0, *)\n    private func ayuPublishSystemUserInterfaceStyle(_ style: UIUserInterfaceStyle) {{\n        if style != .unspecified {{\n            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: style))\n        }}\n    }}\n\n    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {{\n        super.traitCollectionDidChange(previousTraitCollection)\n        if #available(iOS 13.0, *), let windowScene = self.viewIfLoaded?.window?.windowScene {{\n            self.ayuPublishSystemUserInterfaceStyle(windowScene.traitCollection.userInterfaceStyle)\n        }}\n    }}\n\n    @available(iOS 13.0, *)\n    func windowScene(\n        _ windowScene: UIWindowScene,\n        didUpdate previousCoordinateSpace: UICoordinateSpace,\n        interfaceOrientation previousInterfaceOrientation: UIInterfaceOrientation,\n        traitCollection previousTraitCollection: UITraitCollection\n    ) {{\n        self.ayuPublishSystemUserInterfaceStyle(windowScene.traitCollection.userInterfaceStyle)\n    }}\n'''
        window = one(window, old, new, "iOS 27 trait repair")
        window_path.write_text(window, encoding="utf-8")

    # 4) While Auto-Night is active, the visible picker edits its night-theme slot.
    # Otherwise it edits the regular theme and preserves the preferred night theme.
    settings_path = root / "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift"
    settings_controller = settings_path.read_text(encoding="utf-8")
    if PREFERRED_NIGHT_MARK not in settings_controller:
        old = '''            let _ = updatePresentationThemeSettingsInteractively(accountManager: context.sharedContext.accountManager, { current in\n                var updatedAutomaticThemeSwitchSetting = current.automaticThemeSwitchSetting\n                if case let .cloud(info) = updatedTheme, info.theme.settings?.contains(where: { $0.baseTheme == .night || $0.baseTheme == .tinted }) ?? false {\n                    updatedAutomaticThemeSwitchSetting.theme = updatedTheme\n                } else if case let .builtin(theme) = updatedTheme {\n                    if [.day, .dayClassic].contains(theme) {\n                        if updatedAutomaticThemeSwitchSetting.theme.emoticon != nil || [.builtin(.dayClassic), .builtin(.day)].contains(updatedAutomaticThemeSwitchSetting.theme.generalThemeReference) {\n                            updatedAutomaticThemeSwitchSetting.theme = .builtin(.night)\n                        }\n                    } else {\n                        updatedAutomaticThemeSwitchSetting.theme = updatedTheme\n                    }\n                }\n                return current.withUpdatedTheme(updatedTheme).withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)\n\n            }).start()\n'''
        new = f'''            let _ = updatePresentationThemeSettingsInteractively(accountManager: context.sharedContext.accountManager, {{ current in\n                // {PREFERRED_NIGHT_MARK}\n                if autoNightModeTriggered {{\n                    var updatedAutomaticThemeSwitchSetting = current.automaticThemeSwitchSetting\n                    updatedAutomaticThemeSwitchSetting.theme = updatedTheme\n                    return current.withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)\n                }} else {{\n                    return current.withUpdatedTheme(updatedTheme)\n                }}\n            }}).start()\n'''
        settings_controller = one(settings_controller, old, new, "split day/night theme selection")
        settings_path.write_text(settings_controller, encoding="utf-8")

    # Verify exactly the intended repair is present.
    make_verify = make_path.read_text(encoding="utf-8")
    if CLOUD_MARK not in make_verify:
        raise RuntimeError("cloud theme family fallback missing")
    if make_verify.count("ayuCompatibleCloudThemeSettings(") < 3:
        raise RuntimeError("not all cloud theme call sites use family fallback")
    if "return values.first(where: { $0.baseTheme == .classic || $0.baseTheme == .day }) ?? values.first" not in make_verify:
        raise RuntimeError("nil preferred base theme does not default to the light family")

    shared_verify = shared_path.read_text(encoding="utf-8")
    if STATE_MARK not in shared_verify:
        raise RuntimeError("theme state repair missing")
    for required in (
        'theme: .builtin(.dayClassic)',
        'themePreferredBaseTheme: [:]',
        'themeSpecificAccentColors: [:]',
        'automaticThemeSwitchSetting: AutomaticThemeSwitchSetting(force: false, trigger: .system, theme: .builtin(.night))',
    ):
        if required not in shared_verify:
            raise RuntimeError(f"theme state repair incomplete: {required}")

    window_verify = window_path.read_text(encoding="utf-8")
    if TRAIT_MARK not in window_verify:
        raise RuntimeError("iOS 27 trait repair missing")
    if "super.traitCollectionDidChange(previousTraitCollection)" not in window_verify:
        raise RuntimeError("trait propagation missing")
    if "ayuPublishSystemUserInterfaceStyle(windowScene.traitCollection.userInterfaceStyle)" not in window_verify:
        raise RuntimeError("system appearance is not isolated from the window override")
    if "else if #available(iOS 12.0" in window_verify:
        raise RuntimeError("redundant iOS availability branch breaks Swift 6 compilation")
    if "if style != .unspecified" not in window_verify:
        raise RuntimeError("transient unspecified style is not filtered")

    if "ayuApplyFinalThemeAppearance" in shared_verify or "AYU_FINAL_THEME_WINDOW_APPEARANCE" in shared_verify:
        raise RuntimeError("global window appearance override breaks native Liquid Glass")

    settings_verify = settings_path.read_text(encoding="utf-8")
    if PREFERRED_NIGHT_MARK not in settings_verify:
        raise RuntimeError("split day/night theme selection missing")
    if "if autoNightModeTriggered" not in settings_verify:
        raise RuntimeError("active Auto-Night state is not handled")
    if "return current.withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)" not in settings_verify:
        raise RuntimeError("night theme selection is not persisted")
    if "return current.withUpdatedTheme(updatedTheme)" not in settings_verify:
        raise RuntimeError("regular theme selection is not persisted")
    if "return current.withUpdatedTheme(updatedTheme).withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)" in settings_verify:
        raise RuntimeError("main theme selection still overwrites preferred night theme")

    print("[ayu-theme-repair] V3 native Liquid Glass + scene-isolated Auto-Night + split day/night theme selection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
