#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

STATE_MARK = "AYU_THEME_STATE_REPAIR_v1"
CLOUD_MARK = "AYU_CLOUD_THEME_FAMILY_FALLBACK_v1"
TRAIT_MARK = "AYU_IOS27_TRAIT_REPAIR_v1"


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
        helper = f'''import TelegramCore\n\n// {CLOUD_MARK}\nprivate func ayuCompatibleCloudThemeSettings(_ values: [TelegramThemeSettings]?, baseTheme: TelegramBaseTheme?) -> TelegramThemeSettings? {{\n    guard let values, !values.isEmpty else {{\n        return nil\n    }}\n    guard let baseTheme else {{\n        return values.first\n    }}\n    if let exact = values.first(where: {{ $0.baseTheme == baseTheme }}) {{\n        return exact\n    }}\n    let wantsDark = baseTheme == .night || baseTheme == .tinted\n    if let compatible = values.first(where: {{ value in\n        if wantsDark {{\n            return value.baseTheme == .night || value.baseTheme == .tinted\n        }} else {{\n            return value.baseTheme == .classic || value.baseTheme == .day\n        }}\n    }}) {{\n        return compatible\n    }}\n    return values.first\n}}\n\n'''
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

    # 3) iOS 27 can transiently report .unspecified while appearance is changing.
    # Stock Telegram maps that value to light and republishes it. Ignore the transient
    # value and preserve UIViewController trait propagation.
    window_path = root / "submodules/Display/Source/NativeWindowHostView.swift"
    window = window_path.read_text(encoding="utf-8")
    if TRAIT_MARK not in window:
        old = '''    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {\n        if #available(iOS 12.0, *) {\n            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: self.traitCollection.userInterfaceStyle))\n        }\n    }\n'''
        new = f'''    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {{\n        super.traitCollectionDidChange(previousTraitCollection)\n        if #available(iOS 12.0, *) {{\n            // {TRAIT_MARK}\n            let style = self.traitCollection.userInterfaceStyle\n            if style != .unspecified {{\n                self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: style))\n            }}\n        }}\n    }}\n'''
        window = one(window, old, new, "iOS 27 trait repair")
        window_path.write_text(window, encoding="utf-8")

    # Verify exactly the intended repair is present.
    make_verify = make_path.read_text(encoding="utf-8")
    if CLOUD_MARK not in make_verify:
        raise RuntimeError("cloud theme family fallback missing")
    if make_verify.count("ayuCompatibleCloudThemeSettings(") < 3:
        raise RuntimeError("not all cloud theme call sites use family fallback")

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
    if "if style != .unspecified" not in window_verify:
        raise RuntimeError("transient unspecified style is not filtered")

    print("[ayu-theme-repair] reset persisted theme state + compatible custom light/dark variants + iOS 27 trait repair")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
