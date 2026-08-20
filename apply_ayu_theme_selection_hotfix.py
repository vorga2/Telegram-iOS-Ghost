#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_EFFECTIVE_THEME_VARIANT_v0_3"


def replace_exact(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} anchors, found {count}")
    return text.replace(old, new)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_theme_selection_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramPresentationData/Sources/PresentationData.swift"
    if not path.exists():
        raise RuntimeError(f"missing PresentationData source: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print("[ayu-theme] central effective-theme variant fix already installed")
        return 0

    # Telegram already owns light/dark switching. The bug here is narrower: when a
    # cloud theme has multiple base variants and the saved preferred variant belongs
    # to the opposite appearance, preferredBaseTheme becomes nil. makePresentationTheme
    # then falls back to settings.first, which may be the dark variant while the app
    # is light (or vice versa). Resolve the correct cloud variant here, at the single
    # central PresentationData calculation point. No controller refresh, timers,
    # polling, display links or per-frame work.
    old_dark = '''            if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.night, .tinted].contains(baseTheme) {
                preferredBaseTheme = baseTheme
            } else {
                preferredBaseTheme = .night
            }
'''
    new_dark = '''            // AYU_EFFECTIVE_THEME_VARIANT_v0_3
            if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.night, .tinted].contains(baseTheme) {
                preferredBaseTheme = baseTheme
            } else if case let .cloud(info) = effectiveTheme, let baseTheme = info.theme.settings?.first(where: { settings in
                return settings.baseTheme == .night || settings.baseTheme == .tinted
            })?.baseTheme {
                preferredBaseTheme = baseTheme
            } else {
                preferredBaseTheme = .night
            }
'''
    text = replace_exact(text, old_dark, new_dark, 2, "central dark cloud variant")

    old_light = '''            if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.classic, .day].contains(baseTheme) {
                preferredBaseTheme = baseTheme
            }
'''
    new_light = '''            // AYU_EFFECTIVE_THEME_VARIANT_v0_3
            if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.classic, .day].contains(baseTheme) {
                preferredBaseTheme = baseTheme
            } else if case let .cloud(info) = effectiveTheme, let baseTheme = info.theme.settings?.first(where: { settings in
                return settings.baseTheme == .classic || settings.baseTheme == .day
            })?.baseTheme {
                preferredBaseTheme = baseTheme
            }
'''
    text = replace_exact(text, old_light, new_light, 2, "central light cloud variant")

    path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    if verify.count(MARK) != 4:
        raise RuntimeError("central theme marker coverage is incomplete")
    if verify.count("settings.baseTheme == .classic || settings.baseTheme == .day") < 2:
        raise RuntimeError("light cloud variant resolution missing")
    if verify.count("settings.baseTheme == .night || settings.baseTheme == .tinted") < 2:
        raise RuntimeError("dark cloud variant resolution missing")

    print("[ayu-theme] central cloud light/dark variant resolved; Telegram theme pipeline otherwise stock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
