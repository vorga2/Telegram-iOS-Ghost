#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_NATIVE_APPEARANCE_SYNC_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_native_appearance_sync.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Sources/SharedAccountContext.swift"
    if not path.exists():
        raise RuntimeError(f"missing SharedAccountContext: {path}")

    text = path.read_text(encoding="utf-8")
    if MARK in text:
        print("[ayu-native-appearance] already installed")
        return 0

    # Telegram's PresentationTheme is independent of UIKit's system appearance.
    # On iOS 26/27 native UIGlassEffect controls resolve their foreground/tint from
    # UIKit traits. If Telegram switches its own theme without updating the native
    # content subtree, glass controls can stay dark while Telegram is light (or the
    # reverse), making selected icons/text and button/reply backgrounds disappear.
    #
    # Do NOT override UIWindow. mainWindow.systemUserInterfaceStyle is sourced from
    # the window/root controller and is required for Telegram's automatic theme
    # detection. We override only the app content view so native controls inherit
    # the selected Telegram theme while the window can still observe the real OS
    # appearance.
    helper_anchor = "public final class SharedAccountContextImpl: SharedAccountContext {\n"
    helper = '''// AYU_NATIVE_APPEARANCE_SYNC_v0_3\n@available(iOS 13.0, *)\nprivate func ayuSyncNativeAppearance(view: UIView?, presentationData: PresentationData) {\n    guard let view else {\n        return\n    }\n    let style: UIUserInterfaceStyle = presentationData.theme.overallDarkAppearance ? .dark : .light\n    if view.overrideUserInterfaceStyle != style {\n        view.overrideUserInterfaceStyle = style\n        // Force UIKit to resolve dynamic colors/effects immediately. Telegram's\n        // own nodes are refreshed by presentationData; this targets native glass.\n        view.setNeedsLayout()\n        view.layoutIfNeeded()\n    }\n}\n\n'''
    text = one(text, helper_anchor, helper + helper_anchor, "native appearance helper")

    # Live theme changes: run after Telegram has installed its new PresentationData.
    live_anchor = '''                if themeUpdated {\n                    updateLegacyTheme()\n                    \n'''
    live_new = '''                if themeUpdated {\n                    updateLegacyTheme()\n                    if #available(iOS 13.0, *) {\n                        ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.containerView, presentationData: next)\n                    }\n                    \n'''
    text = one(text, live_anchor, live_new, "live theme native sync")

    # Initial state: install matching UIKit appearance before the first user-driven
    # theme transition. Anchor immediately after presentationData is wired up.
    init_anchor = '''        self._presentationData.set(presentationData)\n'''
    init_new = '''        self._presentationData.set(presentationData)\n        if #available(iOS 13.0, *) {\n            ayuSyncNativeAppearance(view: self.mainWindow?.hostView.containerView, presentationData: initialPresentationDataAndSettings.presentationData)\n        }\n'''
    text = one(text, init_anchor, init_new, "initial native appearance sync")

    path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    if verify.count(MARK) != 1:
        raise RuntimeError("native appearance marker missing")
    if "mainWindow?.hostView.containerView" not in verify:
        raise RuntimeError("content-view appearance sync missing")
    # We intentionally leave the stock commented eventView/UIWindow override alone.
    if "ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.eventView" in verify:
        raise RuntimeError("unsafe UIWindow appearance override installed")

    print("[ayu-native-appearance] Telegram theme now drives native Liquid Glass subtree without overriding UIWindow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
