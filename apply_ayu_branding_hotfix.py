#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

MARK = "AYU_APP_DISPLAY_NAME_v0_3"


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

    # Bazel's generated application/extension plist fragment is the authoritative
    # display name for the build used by this repository.
    build_path = root / "Telegram/BUILD"
    build = build_path.read_text(encoding="utf-8")
    if MARK not in build:
        old = '''plist_fragment(
    name = "AppNameInfoPlist",
    extension = "plist",
    template =
    """
    <key>CFBundleDisplayName</key>
    <string>Telegram</string>
'''
        new = f'''# {MARK}
plist_fragment(
    name = "AppNameInfoPlist",
    extension = "plist",
    template =
    """
    <key>CFBundleDisplayName</key>
    <string>AyuGram</string>
'''
        build = one(build, old, new, "Bazel app display name")
        build_path.write_text(build, encoding="utf-8")

    # Keep the project plists consistent for any fallback/project-style build.
    for relative in ("Telegram/Telegram-iOS/InfoBazel.plist", "Telegram/Telegram-iOS/Info.plist"):
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        anchor = "\t<key>CFBundleDisplayName</key>\n\t<string>${APP_NAME}</string>"
        if anchor in text:
            text = text.replace(anchor, "\t<key>CFBundleDisplayName</key>\n\t<string>AyuGram</string>", 1)
            path.write_text(text, encoding="utf-8")

    # A localized InfoPlist.strings can override CFBundleDisplayName. Normalize only
    # that key and leave every permission/localization string untouched.
    for path in (root / "Telegram/Telegram-iOS").glob("*.lproj/InfoPlist.strings"):
        text = path.read_text(encoding="utf-8")
        updated, count = re.subn(
            r'^\s*"CFBundleDisplayName"\s*=\s*"[^"]*"\s*;\s*$',
            '"CFBundleDisplayName" = "AyuGram";',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count:
            path.write_text(updated, encoding="utf-8")

    if "<string>AyuGram</string>" not in build_path.read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram Bazel display name was not installed")

    print("[ayu-branding] CFBundleDisplayName = AyuGram")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
