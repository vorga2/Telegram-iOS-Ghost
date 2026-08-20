#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

MARK = "AYU_EFFECTIVE_THEME_VARIANT_v0_3"


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

    # Telegram already owns theme propagation. The only correction here is choosing
    # the cloud theme variant that matches the effective appearance. Without this,
    # an incompatible saved preferred base leaves preferredBaseTheme nil and the
    # downstream factory falls back to settings.first (which can be a dark variant
    # while the UI is light). This runs only when PresentationData is recalculated.
    dark_pattern = re.compile(
        r'(?P<i>^[ \t]*)if let baseTheme = themeSettings\.themePreferredBaseTheme\[effectiveTheme\.index\], \[\.night, \.tinted\]\.contains\(baseTheme\) \{\n'
        r'(?P=i)    preferredBaseTheme = baseTheme\n'
        r'(?P=i)\} else \{\n'
        r'(?P=i)    preferredBaseTheme = \.night\n'
        r'(?P=i)\}',
        re.MULTILINE,
    )

    def dark_repl(match: re.Match[str]) -> str:
        i = match.group("i")
        return (
            f"{i}// {MARK}\n"
            f"{i}if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.night, .tinted].contains(baseTheme) {{\n"
            f"{i}    preferredBaseTheme = baseTheme\n"
            f"{i}}} else if case let .cloud(info) = effectiveTheme, let baseTheme = info.theme.settings?.first(where: {{ settings in\n"
            f"{i}    return settings.baseTheme == .night || settings.baseTheme == .tinted\n"
            f"{i}}})?.baseTheme {{\n"
            f"{i}    preferredBaseTheme = baseTheme\n"
            f"{i}}} else {{\n"
            f"{i}    preferredBaseTheme = .night\n"
            f"{i}}}"
        )

    text, dark_count = dark_pattern.subn(dark_repl, text)
    if dark_count != 2:
        raise RuntimeError(f"central dark cloud variant: expected 2 anchors, found {dark_count}")

    light_pattern = re.compile(
        r'(?P<i>^[ \t]*)if let baseTheme = themeSettings\.themePreferredBaseTheme\[effectiveTheme\.index\], \[\.classic, \.day\]\.contains\(baseTheme\) \{\n'
        r'(?P=i)    preferredBaseTheme = baseTheme\n'
        r'(?P=i)\}',
        re.MULTILINE,
    )

    def light_repl(match: re.Match[str]) -> str:
        i = match.group("i")
        return (
            f"{i}// {MARK}\n"
            f"{i}if let baseTheme = themeSettings.themePreferredBaseTheme[effectiveTheme.index], [.classic, .day].contains(baseTheme) {{\n"
            f"{i}    preferredBaseTheme = baseTheme\n"
            f"{i}}} else if case let .cloud(info) = effectiveTheme, let baseTheme = info.theme.settings?.first(where: {{ settings in\n"
            f"{i}    return settings.baseTheme == .classic || settings.baseTheme == .day\n"
            f"{i}}})?.baseTheme {{\n"
            f"{i}    preferredBaseTheme = baseTheme\n"
            f"{i}}}"
        )

    text, light_count = light_pattern.subn(light_repl, text)
    if light_count != 2:
        raise RuntimeError(f"central light cloud variant: expected 2 anchors, found {light_count}")

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
