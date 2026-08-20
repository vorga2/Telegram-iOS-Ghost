#!/usr/bin/env python3
from __future__ import annotations

import py_compile
import re
import subprocess
import sys
from pathlib import Path

MAIN_MARK = "AYU_MAIN_APP_BRANDING_v0_3"
EXT_MARK = "AYU_EXTENSION_DISPLAY_NAME_v0_3"
EXT_NAME_MARK = "AYU_ALL_BUNDLE_NAMES_v0_3"
CALLKIT_MARK = "AYU_CALLKIT_DISPLAY_NAME_v0_3"
THEME_MARK = "AYU_EFFECTIVE_THEME_VARIANT_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_branding_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # Apply the central PresentationData cloud-variant fix. It only participates
    # when Telegram already recalculates presentation data; no forced refresh,
    # global trait override, timer, polling or frame callback.
    theme_script = Path(__file__).resolve().with_name("apply_ayu_theme_selection_hotfix.py")
    if not theme_script.exists():
        raise RuntimeError(f"missing theme hotfix: {theme_script}")
    py_compile.compile(str(theme_script), doraise=True)
    subprocess.run([sys.executable, str(theme_script), str(root)], check=True)

    build_path = root / "Telegram/BUILD"
    build = build_path.read_text(encoding="utf-8")

    # Main application plist used by the real Bazel Telegram target.
    if MAIN_MARK not in build:
        old_main = '''    <key>CFBundleDisplayName</key>
    <string>Telegram</string>
    <key>CFBundleIdentifier</key>
    <string>{telegram_bundle_id}</string>
    <key>CFBundleName</key>
    <string>Telegram</string>
'''
        new_main = f'''    <!-- {MAIN_MARK} -->
    <key>CFBundleDisplayName</key>
    <string>AyuGram</string>
    <key>CFBundleIdentifier</key>
    <string>{{telegram_bundle_id}}</string>
    <key>CFBundleName</key>
    <string>AyuGram</string>
'''
        build = one(build, old_main, new_main, "main TelegramInfoPlist branding")

    # AppNameInfoPlist is merged into extensions/widgets.
    if EXT_MARK not in build:
        old_ext = '''plist_fragment(
    name = "AppNameInfoPlist",
    extension = "plist",
    template =
    """
    <key>CFBundleDisplayName</key>
    <string>Telegram</string>
'''
        new_ext = f'''# {EXT_MARK}
plist_fragment(
    name = "AppNameInfoPlist",
    extension = "plist",
    template =
    """
    <key>CFBundleDisplayName</key>
    <string>AyuGram</string>
'''
        build = one(build, old_ext, new_ext, "extension AppNameInfoPlist branding")

    # iOS system services may attribute calls/intents to an embedded extension's
    # CFBundleName rather than the host CFBundleDisplayName. The previous IPA still
    # contained CFBundleName=Telegram in every .appex. Brand those too.
    if EXT_NAME_MARK not in build:
        build = f"# {EXT_NAME_MARK}\n" + build
        build = build.replace(
            "    <key>CFBundleName</key>\n    <string>Telegram</string>\n",
            "    <key>CFBundleName</key>\n    <string>AyuGram</string>\n",
        )

    build_path.write_text(build, encoding="utf-8")

    # Keep project/fallback plists consistent.
    for relative in ("Telegram/Telegram-iOS/InfoBazel.plist", "Telegram/Telegram-iOS/Info.plist"):
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace(
            "\t<key>CFBundleDisplayName</key>\n\t<string>${APP_NAME}</string>",
            "\t<key>CFBundleDisplayName</key>\n\t<string>AyuGram</string>",
        )
        text = text.replace(
            "\t<key>CFBundleDisplayName</key>\n\t<string>Telegram</string>",
            "\t<key>CFBundleDisplayName</key>\n\t<string>AyuGram</string>",
        )
        text = text.replace(
            "\t<key>CFBundleName</key>\n\t<string>$(PRODUCT_NAME)</string>",
            "\t<key>CFBundleName</key>\n\t<string>AyuGram</string>",
        )
        text = text.replace(
            "\t<key>CFBundleName</key>\n\t<string>${PRODUCT_NAME}</string>",
            "\t<key>CFBundleName</key>\n\t<string>AyuGram</string>",
        )
        text = text.replace(
            "\t<key>CFBundleName</key>\n\t<string>Telegram</string>",
            "\t<key>CFBundleName</key>\n\t<string>AyuGram</string>",
        )
        path.write_text(text, encoding="utf-8")

    for path in (root / "Telegram/Telegram-iOS").glob("*.lproj/InfoPlist.strings"):
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r'^\s*"CFBundleDisplayName"\s*=\s*"[^"]*"\s*;\s*$',
            '"CFBundleDisplayName" = "AyuGram";',
            text,
            flags=re.MULTILINE,
        )
        text = re.sub(
            r'^\s*"CFBundleName"\s*=\s*"[^"]*"\s*;\s*$',
            '"CFBundleName" = "AyuGram";',
            text,
            flags=re.MULTILINE,
        )
        path.write_text(text, encoding="utf-8")

    # Keep the explicit CallKit provider label branded as well.
    callkit_path = root / "submodules/TelegramCallsUI/Sources/CallKitIntegration.swift"
    if not callkit_path.exists():
        raise RuntimeError(f"missing CallKit source: {callkit_path}")
    callkit = callkit_path.read_text(encoding="utf-8")
    if CALLKIT_MARK not in callkit:
        old = '        let providerConfiguration = CXProviderConfiguration(localizedName: "Telegram")\n'
        new = (
            f'        // {CALLKIT_MARK}\n'
            '        let providerConfiguration = CXProviderConfiguration(localizedName: "AyuGram")\n'
        )
        callkit = one(callkit, old, new, "CallKit provider display name")
        callkit_path.write_text(callkit, encoding="utf-8")

    verify_build = build_path.read_text(encoding="utf-8")
    required_main = '''    <key>CFBundleDisplayName</key>
    <string>AyuGram</string>
    <key>CFBundleIdentifier</key>
    <string>{telegram_bundle_id}</string>
    <key>CFBundleName</key>
    <string>AyuGram</string>
'''
    if MAIN_MARK not in verify_build or required_main not in verify_build:
        raise RuntimeError("main TelegramInfoPlist was not branded AyuGram")
    if EXT_NAME_MARK not in verify_build:
        raise RuntimeError("embedded bundle-name branding marker missing")
    if "<key>CFBundleName</key>\n    <string>Telegram</string>" in verify_build:
        raise RuntimeError("an embedded bundle still has CFBundleName=Telegram")
    if 'CXProviderConfiguration(localizedName: "AyuGram")' not in callkit_path.read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram CallKit display name was not installed")

    presentation_data = (root / "submodules/TelegramPresentationData/Sources/PresentationData.swift").read_text(encoding="utf-8")
    if presentation_data.count(THEME_MARK) != 4:
        raise RuntimeError("central light/dark cloud-theme resolution is incomplete")

    # These old experiments must stay absent from the fresh Telegram checkout.
    shared = (root / "submodules/TelegramUI/Sources/SharedAccountContext.swift").read_text(encoding="utf-8")
    theme_settings = (root / "submodules/SettingsUI/Sources/Themes/ThemeSettingsController.swift").read_text(encoding="utf-8")
    theme_picker = (root / "submodules/SettingsUI/Sources/ThemePickerController.swift").read_text(encoding="utf-8")
    if "AYU_NATIVE_APPEARANCE_SYNC_v0_3" in shared:
        raise RuntimeError("obsolete global UIKit appearance override is still active")
    if "AYU_THEME_VARIANT_SELECTION_v0_3" in theme_settings or "AYU_THEME_VARIANT_SELECTION_v0_3" in theme_picker:
        raise RuntimeError("obsolete controller-level theme selection workaround is still active")

    print("[ayu-final] central theme variant fix + all AyuGram bundle names + CallKit branding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
