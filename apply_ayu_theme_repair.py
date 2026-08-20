#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

STATE_MARK = "AYU_THEME_STATE_REPAIR_v1"
CLOUD_MARK = "AYU_CLOUD_THEME_FAMILY_FALLBACK_v2"
TRAIT_MARK = "AYU_IOS27_SCENE_TRAIT_REPAIR_v2"
APPEARANCE_MARK = "AYU_FINAL_THEME_WINDOW_APPEARANCE_v2"
PREFERRED_NIGHT_MARK = "AYU_PREFERRED_NIGHT_THEME_PERSISTENCE_v2"


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

    # 3) Keep the actual iOS appearance independent from Telegram's final theme.
    # ThemeRepair v2 overrides the app window so native iOS 27 glass uses the same
    # light/dark palette as PresentationTheme. Reading that overridden trait back
    # into Auto-Night would create feedback, so UIWindowScene is the system source.
    window_path = root / "submodules/Display/Source/NativeWindowHostView.swift"
    window = window_path.read_text(encoding="utf-8")
    if TRAIT_MARK not in window:
        old = '''    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {\n        if #available(iOS 12.0, *) {\n            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: self.traitCollection.userInterfaceStyle))\n        }\n    }\n'''
        new = f'''    // {TRAIT_MARK}\n    @available(iOS 13.0, *)\n    private func ayuPublishSystemUserInterfaceStyle(_ style: UIUserInterfaceStyle) {{\n        if style != .unspecified {{\n            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: style))\n        }}\n    }}\n\n    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {{\n        super.traitCollectionDidChange(previousTraitCollection)\n        if #available(iOS 13.0, *), let windowScene = self.viewIfLoaded?.window?.windowScene {{\n            self.ayuPublishSystemUserInterfaceStyle(windowScene.traitCollection.userInterfaceStyle)\n        }}\n    }}\n\n    @available(iOS 13.0, *)\n    func windowScene(\n        _ windowScene: UIWindowScene,\n        didUpdate previousCoordinateSpace: UICoordinateSpace,\n        interfaceOrientation previousInterfaceOrientation: UIInterfaceOrientation,\n        traitCollection previousTraitCollection: UITraitCollection\n    ) {{\n        self.ayuPublishSystemUserInterfaceStyle(windowScene.traitCollection.userInterfaceStyle)\n    }}\n'''
        window = one(window, old, new, "iOS 27 trait repair")
        window_path.write_text(window, encoding="utf-8")

    # 4) Apply the final Telegram theme to both the content subtree and UIWindow.
    # The previous container-only bridge left window-level iOS 27 glass in a
    # mismatched appearance, making theme-colored text and backgrounds disappear.
    shared = shared_path.read_text(encoding="utf-8")
    if APPEARANCE_MARK not in shared:
        class_anchor = "public final class SharedAccountContextImpl: SharedAccountContext {\n"
        helper = f'''// {APPEARANCE_MARK}\n@available(iOS 13.0, *)\nprivate func ayuApplyFinalThemeAppearance(containerView: UIView?, eventView: UIView?, presentationData: PresentationData) {{\n    let style: UIUserInterfaceStyle = presentationData.theme.overallDarkAppearance ? .dark : .light\n    for view in [eventView, containerView] {{\n        if let view, view.overrideUserInterfaceStyle != style {{\n            view.overrideUserInterfaceStyle = style\n            view.setNeedsLayout()\n        }}\n    }}\n}}\n\n'''
        shared = one(shared, class_anchor, helper + class_anchor, "final theme appearance helper")

        initial_anchor = '''        self._presentationData.set(presentationData)\n'''
        initial_new = '''        self._presentationData.set(presentationData)\n        if #available(iOS 13.0, *) {\n            ayuApplyFinalThemeAppearance(\n                containerView: self.mainWindow?.hostView.containerView,\n                eventView: self.mainWindow?.hostView.eventView,\n                presentationData: initialPresentationDataAndSettings.presentationData\n            )\n        }\n'''
        shared = one(shared, initial_anchor, initial_new, "initial final theme appearance")

        live_anchor = '''                if themeUpdated {\n                    updateLegacyTheme()\n                    \n'''
        live_new = '''                if themeUpdated {\n                    if #available(iOS 13.0, *) {\n                        ayuApplyFinalThemeAppearance(\n                            containerView: strongSelf.mainWindow?.hostView.containerView,\n                            eventView: strongSelf.mainWindow?.hostView.eventView,\n                            presentationData: next\n                        )\n                    }\n                    updateLegacyTheme()\n                    \n'''
        shared = one(shared, live_anchor, live_new, "live final theme appearance")
        shared_path.write_text(shared, encoding="utf-8")

    # 5) Main Appearance selection must not overwrite the separately selected
    # preferred Auto-Night theme. The Auto-Night controller remains its sole owner.
    settings_path = root / "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift"
    settings_controller = settings_path.read_text(encoding="utf-8")
    if PREFERRED_NIGHT_MARK not in settings_controller:
        old = '''            let _ = updatePresentationThemeSettingsInteractively(accountManager: context.sharedContext.accountManager, { current in\n                var updatedAutomaticThemeSwitchSetting = current.automaticThemeSwitchSetting\n                if case let .cloud(info) = updatedTheme, info.theme.settings?.contains(where: { $0.baseTheme == .night || $0.baseTheme == .tinted }) ?? false {\n                    updatedAutomaticThemeSwitchSetting.theme = updatedTheme\n                } else if case let .builtin(theme) = updatedTheme {\n                    if [.day, .dayClassic].contains(theme) {\n                        if updatedAutomaticThemeSwitchSetting.theme.emoticon != nil || [.builtin(.dayClassic), .builtin(.day)].contains(updatedAutomaticThemeSwitchSetting.theme.generalThemeReference) {\n                            updatedAutomaticThemeSwitchSetting.theme = .builtin(.night)\n                        }\n                    } else {\n                        updatedAutomaticThemeSwitchSetting.theme = updatedTheme\n                    }\n                }\n                return current.withUpdatedTheme(updatedTheme).withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)\n\n            }).start()\n'''
        new = f'''            let _ = updatePresentationThemeSettingsInteractively(accountManager: context.sharedContext.accountManager, {{ current in\n                // {PREFERRED_NIGHT_MARK}\n                // Re-selecting a main light/dark theme must not silently replace\n                // the independent preferred theme chosen in Auto-Night.\n                return current.withUpdatedTheme(updatedTheme)\n            }}).start()\n'''
        settings_controller = one(settings_controller, old, new, "preferred night theme persistence")
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

    shared_verify = shared_path.read_text(encoding="utf-8")
    if APPEARANCE_MARK not in shared_verify:
        raise RuntimeError("final theme window appearance bridge missing")
    if "eventView: strongSelf.mainWindow?.hostView.eventView" not in shared_verify:
        raise RuntimeError("window-level final theme appearance missing")
    update_index = shared_verify.find("if themeUpdated")
    appearance_index = shared_verify.find("ayuApplyFinalThemeAppearance(", update_index)
    legacy_index = shared_verify.find("updateLegacyTheme()", update_index)
    if update_index < 0 or appearance_index < 0 or legacy_index < 0 or appearance_index > legacy_index:
        raise RuntimeError("final appearance must be installed before legacy theme redraw")

    settings_verify = settings_path.read_text(encoding="utf-8")
    if PREFERRED_NIGHT_MARK not in settings_verify:
        raise RuntimeError("preferred night theme persistence missing")
    if "return current.withUpdatedTheme(updatedTheme).withUpdatedAutomaticThemeSwitchSetting(updatedAutomaticThemeSwitchSetting)" in settings_verify:
        raise RuntimeError("main theme selection still overwrites preferred night theme")

    print("[ayu-theme-repair] V2 final window palette + scene-isolated Auto-Night + persistent preferred night theme")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
