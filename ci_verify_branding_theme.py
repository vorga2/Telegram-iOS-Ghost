#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent)).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    telegram = runner_temp / "Telegram-iOS"
    require(telegram.exists(), "Telegram-iOS checkout is missing")

    theme = workspace / "apply_ayu_theme_selection_hotfix.py"
    branding = workspace / "apply_ayu_branding_hotfix.py"
    py_compile.compile(str(theme), doraise=True)
    py_compile.compile(str(branding), doraise=True)

    # Match the real IPA build: branding invokes the central theme patch itself.
    subprocess.run([sys.executable, str(branding), str(telegram)], check=True)

    build = (telegram / "Telegram/BUILD").read_text(encoding="utf-8")
    require("AYU_MAIN_APP_BRANDING_v0_3" in build, "main app branding marker missing")
    require("AYU_ALL_BUNDLE_NAMES_v0_3" in build, "all-bundle branding marker missing")
    require('''<key>CFBundleDisplayName</key>\n    <string>AyuGram</string>\n    <key>CFBundleIdentifier</key>\n    <string>{telegram_bundle_id}</string>\n    <key>CFBundleName</key>\n    <string>AyuGram</string>''' in build, "main TelegramInfoPlist is not AyuGram")
    require('''ios_application(\n    name = "Telegram",''' in build, "main Telegram target missing")
    require(''':TelegramInfoPlist''' in build, "main app is not using TelegramInfoPlist")
    require("<key>CFBundleName</key>\n    <string>Telegram</string>" not in build, "an embedded bundle still advertises CFBundleName=Telegram")

    callkit = (telegram / "submodules/TelegramCallsUI/Sources/CallKitIntegration.swift").read_text(encoding="utf-8")
    require("AYU_CALLKIT_DISPLAY_NAME_v0_3" in callkit, "CallKit branding marker missing")
    require('CXProviderConfiguration(localizedName: "AyuGram")' in callkit, "CallKit provider still says Telegram")

    presentation_data = (telegram / "submodules/TelegramPresentationData/Sources/PresentationData.swift").read_text(encoding="utf-8")
    require(presentation_data.count("AYU_EFFECTIVE_THEME_VARIANT_v0_3") == 4, "central theme variant fix must cover initial + live light/dark paths")
    require(presentation_data.count("settings.baseTheme == .classic || settings.baseTheme == .day") >= 2, "central light cloud-theme resolution missing")
    require(presentation_data.count("settings.baseTheme == .night || settings.baseTheme == .tinted") >= 2, "central dark cloud-theme resolution missing")

    # The previous workaround changed theme-selection controllers and globally
    # forced UIKit traits. Both are intentionally absent now: Telegram's normal
    # theme pipeline owns updates, while PresentationData only resolves the right
    # cloud variant.
    shared = (telegram / "submodules/TelegramUI/Sources/SharedAccountContext.swift").read_text(encoding="utf-8")
    theme_settings = (telegram / "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift").read_text(encoding="utf-8")
    theme_picker = (telegram / "submodules/SettingsUI/Sources/ThemePickerController.swift").read_text(encoding="utf-8")
    require("AYU_NATIVE_APPEARANCE_SYNC_v0_3" not in shared, "obsolete global UIKit appearance override is active")
    require("AYU_THEME_VARIANT_SELECTION_v0_3" not in theme_settings, "obsolete ThemeSettings controller workaround is active")
    require("AYU_THEME_VARIANT_SELECTION_v0_3" not in theme_picker, "obsolete ThemePicker controller workaround is active")

    app_delegate = (telegram / "submodules/TelegramUI/Sources/AppDelegate.swift").read_text(encoding="utf-8")
    require("AYU_CALL_STATUS_PILL_v0_3" not in app_delegate, "obsolete app-window fake status pill is still injected")

    print("=== BRANDING + CENTRAL THEME VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== BRANDING + CENTRAL THEME VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
