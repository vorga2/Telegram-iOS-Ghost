#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


STATE_MARK = "AYU_THEME_STOCK_ROUTING_RECOVERY_v6"
ALPHA_MARK = "AYU_LEGACY_THEME_ACCENT_ALPHA_v4"


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
        // Legacy Ayu builds wrote a day-based palette into Telegram's manual
        // night slot, so dark custom themes — including ones that render dark
        // but are declared on a day base — could never occupy the night slot:
        // the switch showed stock Night and custom themes looked mixed. Repair
        // the slot ONCE by actually rendering the candidate references and
        // preferring the user's own theme when it renders dark. The stock
        // `force` flag, accents, bubbles and wallpapers stay untouched.
        if applicationBindings.isMainApp {{
            let recoveryKey = "com.nomadvorga.telegram.ayu.themeStockRoutingRecovery.v6"
            if !UserDefaults.standard.bool(forKey: recoveryKey) {{
                let _ = updatePresentationThemeSettingsInteractively(accountManager: accountManager, {{ current in
                    func ayuReferenceRendersDark(_ reference: PresentationThemeReference) -> Bool {{
                        if let builtTheme = makePresentationTheme(mediaBox: accountManager.mediaBox, themeReference: reference) {{
                            return builtTheme.overallDarkAppearance
                        }}
                        switch reference {{
                        case .builtin(let builtin):
                            switch builtin.baseTheme {{
                            case .night, .tinted:
                                return true
                            case .classic, .day:
                                return false
                            }}
                        case .cloud(let info):
                            return info.theme.settings?.contains(where: {{ $0.baseTheme == .night || $0.baseTheme == .tinted }}) ?? false
                        case .local:
                            return false
                        }}
                    }}

                    var automaticThemeSwitchSetting = current.automaticThemeSwitchSetting
                    if !ayuReferenceRendersDark(automaticThemeSwitchSetting.theme) {{
                        automaticThemeSwitchSetting.theme = ayuReferenceRendersDark(current.theme) ? current.theme : .builtin(.night)
                    }}

                    // ThemeRepair v3 wrote explicitNone, which disables auto-night entirely.
                    if case .explicitNone = automaticThemeSwitchSetting.trigger {{
                        automaticThemeSwitchSetting.trigger = .system
                    }}

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
    path.write_text(one(text, anchor, replacement, "stock theme routing recovery"), encoding="utf-8")


def patch_accent_alpha(root: Path) -> None:
    path = root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift"
    text = path.read_text(encoding="utf-8")
    if ALPHA_MARK in text:
        return

    import_anchor = "import TelegramCore\n\n"
    helper = f'''import TelegramCore

// {ALPHA_MARK}
// Some preferences written by old Ayu builds contain RGB24 in Telegram's ARGB
// field. Normalize only alpha-zero legacy values. RGB and every valid ARGB value
// remain unchanged, so theme-family and custom-wallpaper routing stay stock.
private func ayuThemeAccentColor(_ value: UInt32) -> UIColor {{
    if value & 0xff000000 == 0 {{
        return UIColor(rgb: value)
    }} else {{
        return UIColor(argb: value)
    }}
}}

'''
    text = one(text, import_anchor, helper, "legacy accent helper")

    accent_count = text.count("UIColor(argb: settings.accentColor)")
    outgoing_count = text.count("UIColor(argb: $0)")
    if accent_count != 4 or outgoing_count != 4:
        raise RuntimeError(f"theme accent alpha: expected 4+4 anchors, found {accent_count}+{outgoing_count}")
    text = text.replace("UIColor(argb: settings.accentColor)", "ayuThemeAccentColor(settings.accentColor)")
    text = text.replace("UIColor(argb: $0)", "ayuThemeAccentColor($0)")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_theme_integrity.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_state(root)
    patch_accent_alpha(root)

    shared = (root / "submodules/TelegramUI/Sources/SharedAccountContext.swift").read_text(encoding="utf-8")
    make = (root / "submodules/TelegramPresentationData/Sources/MakePresentationTheme.swift").read_text(encoding="utf-8")
    presentation = (root / "submodules/TelegramPresentationData/Sources/PresentationData.swift").read_text(encoding="utf-8")
    for required, value in (
        (STATE_MARK, shared),
        (ALPHA_MARK, make),
        ("ayuReferenceRendersDark", shared),
        ("automaticThemeSwitchSetting.theme = ayuReferenceRendersDark(current.theme) ? current.theme : .builtin(.night)", shared),
        ("case .explicitNone = automaticThemeSwitchSetting.trigger", shared),
        ("themeSpecificAccentColors: current.themeSpecificAccentColors", shared),
        ("themeSpecificChatWallpapers: current.themeSpecificChatWallpapers", shared),
        ("accentColor: ayuThemeAccentColor(settings.accentColor)", make),
    ):
        if required not in value:
            raise RuntimeError(f"theme integrity incomplete: {required}")

    if "ayuCompatibleThemeSettings" in make or "ayuManualThemeBase" in presentation:
        raise RuntimeError("non-stock theme family routing returned")

    print("[ayu-theme-integrity] night-slot routing repaired once; stock Telegram day/night and custom-wallpaper routing preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
