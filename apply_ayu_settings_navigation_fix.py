#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_SETTINGS_NAVIGATION_FIX_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_settings_navigation_fix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    text = path.read_text(encoding="utf-8")

    if MARK in text:
        print(f"[ayu-settings-navigation] already patched: {path}")
        return 0

    old = '''    let arguments = AyuMainArguments(openGhost: { [weak controllerBox] in
        controllerBox?.value?.push(ayuGhostSettingsController(context: context))
    }, openCustomization: { [weak controllerBox] in
        controllerBox?.value?.push(ayuCustomizationController(context: context))
    }, openSpy: { [weak controllerBox] in
        controllerBox?.value?.push(ayuSpySettingsController(context: context))
    })
'''

    new = '''    // AYU_SETTINGS_NAVIGATION_FIX_v0_3
    // AyuWeakControllerBox already stores its controller weakly. The closures must
    // retain the box itself; otherwise the local box is released when this factory
    // returns and every category action becomes a no-op.
    let arguments = AyuMainArguments(openGhost: {
        controllerBox.value?.push(ayuGhostSettingsController(context: context))
    }, openCustomization: {
        controllerBox.value?.push(ayuCustomizationController(context: context))
    }, openSpy: {
        controllerBox.value?.push(ayuSpySettingsController(context: context))
    })
'''

    text = one(text, old, new, "main category navigation closures")
    path.write_text(text, encoding="utf-8")
    print("[ayu-settings-navigation] category controller box lifetime fixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
