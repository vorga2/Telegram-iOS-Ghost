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

    # Branding intentionally invokes the theme hotfix too, matching the real IPA build.
    subprocess.run([sys.executable, str(branding), str(telegram)], check=True)

    build = (telegram / "Telegram/BUILD").read_text(encoding="utf-8")
    require("AYU_MAIN_APP_BRANDING_v0_3" in build, "main app branding marker missing")
    require('''<key>CFBundleDisplayName</key>\n    <string>AyuGram</string>\n    <key>CFBundleIdentifier</key>\n    <string>{telegram_bundle_id}</string>\n    <key>CFBundleName</key>\n    <string>AyuGram</string>''' in build, "main TelegramInfoPlist is not AyuGram")
    require('''ios_application(\n    name = "Telegram",''' in build, "main Telegram target missing")
    require(''':TelegramInfoPlist''' in build, "main app is not using TelegramInfoPlist")

    callkit = (telegram / "submodules/TelegramCallsUI/Sources/CallKitIntegration.swift").read_text(encoding="utf-8")
    require("AYU_CALLKIT_DISPLAY_NAME_v0_3" in callkit, "CallKit branding marker missing")
    require('CXProviderConfiguration(localizedName: "AyuGram")' in callkit, "CallKit provider still says Telegram")

    shared = (telegram / "submodules/TelegramUI/Sources/SharedAccountContext.swift").read_text(encoding="utf-8")
    require("AYU_NATIVE_APPEARANCE_SYNC_v0_3" in shared, "native UIKit appearance sync missing")
    require("eventView.overrideUserInterfaceStyle = userInterfaceStyle" in shared, "UIKit light/dark sync assignment missing")

    theme_settings = (telegram / "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift").read_text(encoding="utf-8")
    theme_picker = (telegram / "submodules/SettingsUI/Sources/ThemePickerController.swift").read_text(encoding="utf-8")
    for name, text in (("ThemeSettingsController", theme_settings), ("ThemePickerController", theme_picker)):
        require("AYU_THEME_VARIANT_SELECTION_v0_3" in text, f"{name}: theme variant fix missing")
        require("baseTheme: ayuSelectedBaseTheme" in text, f"{name}: resolved base theme is not used")
        require("overallDarkAppearance" in text, f"{name}: current light/dark appearance is not consulted")

    app_delegate = (telegram / "submodules/TelegramUI/Sources/AppDelegate.swift").read_text(encoding="utf-8")
    require("AYU_CALL_STATUS_PILL_v0_3" not in app_delegate, "obsolete app-window fake status pill is still injected")

    print("=== BRANDING + THEME VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== BRANDING + THEME VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
