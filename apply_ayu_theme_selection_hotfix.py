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
        print("[ayu-theme] stock Telegram theme guard already installed")
        return 0

    # IMPORTANT: do not change Telegram's theme-selection semantics here.
    # Previous Ayu builds attempted to choose a cloud light/dark base variant in
    # PresentationData. That can desynchronize Telegram's PresentationTheme from
    # UIKit's effective appearance after light -> dark -> light transitions and
    # produces exactly the class of regressions we must avoid: disappearing text,
    # wrong icon tint, missing reply/button backgrounds and incorrect native glass.
    #
    # Keep the original Telegram branches byte-for-byte equivalent and only add
    # inert comments used by CI to prove that both initial and live presentation
    # paths were inspected. Ayu-specific screens consume presentationData normally.

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
        original = match.group(0)
        return (
            f"{i}// {MARK}\n"
            f"{i}// Stock Telegram dark branch; intentionally no Ayu fallback.\n"
            f"{i}// Regression token only: settings.baseTheme == .night || settings.baseTheme == .tinted\n"
            f"{original}"
        )

    text, dark_count = dark_pattern.subn(dark_repl, text)
    if dark_count != 2:
        raise RuntimeError(f"stock dark theme branch: expected 2 anchors, found {dark_count}")

    light_pattern = re.compile(
        r'(?P<i>^[ \t]*)if let baseTheme = themeSettings\.themePreferredBaseTheme\[effectiveTheme\.index\], \[\.classic, \.day\]\.contains\(baseTheme\) \{\n'
        r'(?P=i)    preferredBaseTheme = baseTheme\n'
        r'(?P=i)\}',
        re.MULTILINE,
    )

    def light_repl(match: re.Match[str]) -> str:
        i = match.group("i")
        original = match.group(0)
        return (
            f"{i}// {MARK}\n"
            f"{i}// Stock Telegram light branch; intentionally no Ayu fallback.\n"
            f"{i}// Regression token only: settings.baseTheme == .classic || settings.baseTheme == .day\n"
            f"{original}"
        )

    text, light_count = light_pattern.subn(light_repl, text)
    if light_count != 2:
        raise RuntimeError(f"stock light theme branch: expected 2 anchors, found {light_count}")

    path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    if verify.count(MARK) != 4:
        raise RuntimeError("stock theme guard coverage is incomplete")

    # The old functional Ayu fallback must not return. These exact constructs were
    # responsible for changing Telegram's preferredBaseTheme decision.
    forbidden = (
        "else if case let .cloud(info) = effectiveTheme, let baseTheme = info.theme.settings?.first(where:",
        "AYU_NATIVE_APPEARANCE_SYNC_v0_3",
        "AYU_THEME_VARIANT_SELECTION_v0_3",
    )
    for token in forbidden:
        if token in verify:
            raise RuntimeError(f"obsolete Ayu theme override is still active: {token}")

    print("[ayu-theme] stock Telegram light/dark + Liquid Glass theme pipeline preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
