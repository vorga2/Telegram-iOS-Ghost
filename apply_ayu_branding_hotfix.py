#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

MAIN_MARK = "AYU_MAIN_APP_BRANDING_v0_3"
EXT_MARK = "AYU_EXTENSION_DISPLAY_NAME_v0_3"
CALLKIT_MARK = "AYU_CALLKIT_DISPLAY_NAME_v0_3"


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

    # The real Bazel host app uses :TelegramInfoPlist, not :AppNameInfoPlist.
    # Patch both CFBundleDisplayName and CFBundleName in that MAIN app plist.
    build_path = root / "Telegram/BUILD"
    build = build_path.read_text(encoding="utf-8")
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

    # Extensions/widgets use AppNameInfoPlist. Keep them branded consistently.
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

    build_path.write_text(build, encoding="utf-8")

    # Keep project/fallback plists consistent as well. These are not the primary
    # Bazel source for the release IPA, but must not reintroduce Telegram branding.
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

    # Localized InfoPlist.strings may override bundle naming on the device.
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

    # Older/current CallKit paths can still retain the provider name separately.
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
    if 'CXProviderConfiguration(localizedName: "AyuGram")' not in callkit_path.read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram CallKit display name was not installed")

    print("[ayu-branding] MAIN TelegramInfoPlist display/name + extensions + CallKit = AyuGram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
