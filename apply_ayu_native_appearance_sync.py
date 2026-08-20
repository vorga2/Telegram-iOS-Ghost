#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MARK = "AYU_NATIVE_APPEARANCE_SYNC_v0_3"
LENS_MARK = "AYU_LIQUID_LENS_APPEARANCE_SYNC_v0_3"
CHAT_MARK = "AYU_VISIBLE_CHAT_LIST_BRANDING_v0_3"


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
    # iOS 26. Keep that private native lens on the same effective appearance there;
    # the iOS 27-specific repair below deliberately bypasses the private lens on 27+.
    lens_path = root / "submodules/TelegramUI/Components/LiquidLens/Sources/LiquidLensView.swift"
    if not lens_path.exists():
        raise RuntimeError(f"missing LiquidLensView: {lens_path}")
    lens = lens_path.read_text(encoding="utf-8")
    if LENS_MARK not in lens:
        lens_anchor = '''    private func update(params: Params, transition: ComponentTransition) {\n        let isFirstTime = self.params == nil\n'''
        lens_new = '''    private func update(params: Params, transition: ComponentTransition) {\n        // AYU_LIQUID_LENS_APPEARANCE_SYNC_v0_3\n        if #available(iOS 26.0, *), let lensView = self.lensView {\n            let style: UIUserInterfaceStyle = params.isDark ? .dark : .light\n            if lensView.overrideUserInterfaceStyle != style {\n                lensView.overrideUserInterfaceStyle = style\n                lensView.setNeedsLayout()\n            }\n        }\n\n        let isFirstTime = self.params == nil\n'''
        lens = one(lens, lens_anchor, lens_new, "LiquidLens selected appearance")
        lens_path.write_text(lens, encoding="utf-8")

    # 3) Main chat-list branding is rendered inside Telegram itself. Bundle/CallKit
    # names do not affect it. Brand both the plain header path and the live network
    # status title path, while leaving the bottom localized "Chats" tab alone.
    chat_path = root / "submodules/ChatListUI/Sources/ChatListController.swift"
    if not chat_path.exists():
        raise RuntimeError(f"missing ChatListController: {chat_path}")
    chat = chat_path.read_text(encoding="utf-8")
    if CHAT_MARK not in chat:
        initial_anchor = '''            if groupId == .root {\n                title = self.presentationData.strings.DialogList_Title\n            } else {\n'''
        initial_new = '''            if groupId == .root {\n                // AYU_VISIBLE_CHAT_LIST_BRANDING_v0_3\n                title = "AyuGram"\n            } else {\n'''
        chat = one(chat, initial_anchor, initial_new, "visible root chat-list title")

        live_anchor = '''            if groupId == .root {\n                defaultTitle = presentationData.strings.DialogList_Title\n            } else {\n'''
        live_new = '''            if groupId == .root {\n                defaultTitle = "AyuGram"\n            } else {\n'''
        chat = one(chat, live_anchor, live_new, "live root chat-list title")
        chat_path.write_text(chat, encoding="utf-8")

    # 4) iOS 27 has separate Liquid Glass / trait regressions. Apply targeted
    # runtime repairs after the generic theme bridge so the fixes compose cleanly.
    ios27_script = Path(__file__).resolve().with_name("apply_ayu_ios27_render_fix.py")
    if not ios27_script.exists():
        raise RuntimeError(f"missing iOS 27 render fix: {ios27_script}")
    subprocess.run([sys.executable, str(ios27_script), str(root)], check=True)

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
    if "AYU_IOS27_LIQUID_LENS_FALLBACK_v0_3" not in lens_verify:
        raise RuntimeError("iOS 27 LiquidLens fallback missing")

    chat_verify = chat_path.read_text(encoding="utf-8")
    if chat_verify.count(CHAT_MARK) != 1:
        raise RuntimeError("visible chat-list branding marker missing")
    if 'title = "AyuGram"' not in chat_verify or 'defaultTitle = "AyuGram"' not in chat_verify:
        raise RuntimeError("AyuGram root chat-list runtime title is incomplete")
    if "AYU_VISIBLE_CHAT_LIST_FINAL_TITLE_v0_3" not in chat_verify:
        raise RuntimeError("final visible ChatListTitleView branding is missing")

    print("[ayu-native-appearance] Telegram theme bridge + iOS 27 render repair + final AyuGram visible title installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
