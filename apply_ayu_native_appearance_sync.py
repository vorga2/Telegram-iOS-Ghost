#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_NATIVE_APPEARANCE_SYNC_v0_3"
LENS_MARK = "AYU_LIQUID_LENS_APPEARANCE_SYNC_v0_3"


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

    # 1) Bridge Telegram's PresentationTheme into UIKit's app-content subtree.
    # Do not override UIWindow: the window/root controller remains Telegram's source
    # of truth for the real system appearance used by automatic theme switching.
    shared_path = root / "submodules/TelegramUI/Sources/SharedAccountContext.swift"
    if not shared_path.exists():
        raise RuntimeError(f"missing SharedAccountContext: {shared_path}")
    shared = shared_path.read_text(encoding="utf-8")

    if MARK not in shared:
        helper_anchor = "public final class SharedAccountContextImpl: SharedAccountContext {\n"
        helper = '''// AYU_NATIVE_APPEARANCE_SYNC_v0_3\n@available(iOS 13.0, *)\nprivate func ayuSyncNativeAppearance(view: UIView?, presentationData: PresentationData) {\n    guard let view else {\n        return\n    }\n    let style: UIUserInterfaceStyle = presentationData.theme.overallDarkAppearance ? .dark : .light\n    if view.overrideUserInterfaceStyle != style {\n        view.overrideUserInterfaceStyle = style\n        view.setNeedsLayout()\n        view.layoutIfNeeded()\n    }\n}\n\n'''
        shared = one(shared, helper_anchor, helper + helper_anchor, "native appearance helper")

        live_anchor = '''                if themeUpdated {\n                    updateLegacyTheme()\n                    \n'''
        live_new = '''                if themeUpdated {\n                    updateLegacyTheme()\n                    if #available(iOS 13.0, *) {\n                        ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.containerView, presentationData: next)\n                    }\n                    \n'''
        shared = one(shared, live_anchor, live_new, "live theme native sync")

        init_anchor = '''        self._presentationData.set(presentationData)\n'''
        init_new = '''        self._presentationData.set(presentationData)\n        if #available(iOS 13.0, *) {\n            ayuSyncNativeAppearance(view: self.mainWindow?.hostView.containerView, presentationData: initialPresentationDataAndSettings.presentationData)\n        }\n'''
        shared = one(shared, init_anchor, init_new, "initial native appearance sync")
        shared_path.write_text(shared, encoding="utf-8")

    # 2) Selected tab/category content is rendered through _UILiquidLensView on
    # iOS 26+. Unlike GlassBackgroundView, stock LiquidLensView never applies the
    # supplied isDark value to that native view. After dark -> light the lens can
    # therefore keep dark traits and its selected icon becomes effectively invisible.
    lens_path = root / "submodules/TelegramUI/Components/LiquidLens/Sources/LiquidLensView.swift"
    if not lens_path.exists():
        raise RuntimeError(f"missing LiquidLensView: {lens_path}")
    lens = lens_path.read_text(encoding="utf-8")
    if LENS_MARK not in lens:
        lens_anchor = '''    private func update(params: Params, transition: ComponentTransition) {\n        let isFirstTime = self.params == nil\n'''
        lens_new = '''    private func update(params: Params, transition: ComponentTransition) {\n        // AYU_LIQUID_LENS_APPEARANCE_SYNC_v0_3\n        // GlassBackgroundView already does this. Keep the private native lens on\n        // the same effective appearance so selected content uses the right tint.\n        if #available(iOS 26.0, *), let lensView = self.lensView {\n            let style: UIUserInterfaceStyle = params.isDark ? .dark : .light\n            if lensView.overrideUserInterfaceStyle != style {\n                lensView.overrideUserInterfaceStyle = style\n                lensView.setNeedsLayout()\n            }\n        }\n\n        let isFirstTime = self.params == nil\n'''
        lens = one(lens, lens_anchor, lens_new, "LiquidLens selected appearance")
        lens_path.write_text(lens, encoding="utf-8")

    shared_verify = shared_path.read_text(encoding="utf-8")
    if shared_verify.count(MARK) != 1:
        raise RuntimeError("native appearance marker missing")
    if "ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.containerView" not in shared_verify:
        raise RuntimeError("live content-view appearance sync missing")
    if "ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.eventView" in shared_verify:
        raise RuntimeError("unsafe UIWindow appearance override installed")

    lens_verify = lens_path.read_text(encoding="utf-8")
    if lens_verify.count(LENS_MARK) != 1:
        raise RuntimeError("LiquidLens appearance marker missing")
    if "lensView.overrideUserInterfaceStyle = style" not in lens_verify:
        raise RuntimeError("LiquidLens native style assignment missing")

    print("[ayu-native-appearance] Telegram content + selected Liquid Lens now track PresentationTheme")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
