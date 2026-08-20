#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

LENS_FALLBACK_MARK = "AYU_IOS27_LIQUID_LENS_FALLBACK_v0_3"
TAB_REBUILD_MARK = "AYU_TABBAR_THEME_REBUILD_v0_3"
TAB_IMMEDIATE_MARK = "AYU_TABBAR_THEME_IMMEDIATE_UPDATE_v0_3"
TRAIT_MARK = "AYU_IOS27_TRAIT_SYNC_v0_3"
PRESENTATION_ORDER_MARK = "AYU_THEME_APPEARANCE_BEFORE_LEGACY_v0_3"
CHAT_FINAL_MARK = "AYU_VISIBLE_CHAT_LIST_FINAL_TITLE_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_ios27_render_fix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # iOS 27 currently has regressions in the private _UILiquidLensView path used by
    # Telegram for selected tab/category content. Keep Telegram's native public
    # GlassBackgroundView, but use Telegram's already-existing legacy selection lens
    # implementation on iOS 27+. This keeps Liquid Glass surfaces while avoiding the
    # private selection compositor that can hide selected icons after a theme switch.
    lens_path = root / "submodules/TelegramUI/Components/LiquidLens/Sources/LiquidLensView.swift"
    lens = lens_path.read_text(encoding="utf-8")
    if LENS_FALLBACK_MARK not in lens:
        old = '''        if #available(iOS 26.0, *) {\n            if let viewClass = NSClassFromString("_UILiquidLensView") as AnyObject as? NSObjectProtocol {\n'''
        new = f'''        // {LENS_FALLBACK_MARK}\n        if #available(iOS 26.0, *), ProcessInfo.processInfo.operatingSystemVersion.majorVersion < 27 {{\n            if let viewClass = NSClassFromString("_UILiquidLensView") as AnyObject as? NSObjectProtocol {{\n'''
        lens = one(lens, old, new, "iOS 27 LiquidLens fallback")
        lens_path.write_text(lens, encoding="utf-8")

    # TabBarComponent keeps two component trees per item: normal content and selected
    # content. Rebuild both trees only when PresentationTheme identity changes so no
    # stale template tint survives dark -> light or light -> dark.
    tab_path = root / "submodules/TelegramUI/Components/TabBarComponent/Sources/TabBarComponent.swift"
    tab = tab_path.read_text(encoding="utf-8")
    if TAB_REBUILD_MARK not in tab:
        old = '''            let previousComponent = self.component\n            self.component = component\n            self.state = state\n            \n            self.overrideUserInterfaceStyle = component.theme.overallDarkAppearance ? .dark : .light\n'''
        new = f'''            let previousComponent = self.component\n\n            // {TAB_REBUILD_MARK}\n            if let previousComponent, previousComponent.theme !== component.theme {{\n                for (_, itemView) in self.itemViews {{\n                    itemView.view?.removeFromSuperview()\n                }}\n                for (_, selectedItemView) in self.selectedItemViews {{\n                    selectedItemView.view?.removeFromSuperview()\n                }}\n                self.itemViews.removeAll(keepingCapacity: true)\n                self.selectedItemViews.removeAll(keepingCapacity: true)\n                self.measureItemViews.removeAll(keepingCapacity: true)\n            }}\n\n            self.component = component\n            self.state = state\n            \n            let ayuInterfaceStyle: UIUserInterfaceStyle = component.theme.overallDarkAppearance ? .dark : .light\n            self.overrideUserInterfaceStyle = ayuInterfaceStyle\n            self.liquidLensView.contentView.overrideUserInterfaceStyle = ayuInterfaceStyle\n            self.liquidLensView.selectedContentView.overrideUserInterfaceStyle = ayuInterfaceStyle\n'''
        tab = one(tab, old, new, "TabBar selected/normal theme rebuild")
        tab_path.write_text(tab, encoding="utf-8")

    # The stock node only schedules a future layout after changing the theme. Render
    # the existing tab bar immediately when a layout is already known, so selected
    # icon/text colors cannot lag one layout pass behind the rest of the app.
    tab_node_path = root / "submodules/TabBarUI/Sources/TabBarContollerNode.swift"
    tab_node = tab_node_path.read_text(encoding="utf-8")
    if TAB_IMMEDIATE_MARK not in tab_node:
        old = '''    func updateTheme(_ theme: PresentationTheme) {\n        self.theme = theme\n        self.backgroundColor = theme.list.plainBackgroundColor\n        \n        self.disabledOverlayNode.backgroundColor = theme.rootController.tabBar.backgroundColor.withAlphaComponent(0.5)\n        self.requestUpdate()\n    }\n'''
        new = f'''    func updateTheme(_ theme: PresentationTheme) {{\n        self.theme = theme\n        self.backgroundColor = theme.list.plainBackgroundColor\n        \n        self.disabledOverlayNode.backgroundColor = theme.rootController.tabBar.backgroundColor.withAlphaComponent(0.5)\n        // {TAB_IMMEDIATE_MARK}\n        if let layoutResult = self.layoutResult {{\n            self.isUpdateRequested = false\n            let _ = self.updateImpl(params: layoutResult.params, transition: .immediate)\n        }} else {{\n            self.requestUpdate()\n        }}\n    }}\n'''
        tab_node = one(tab_node, old, new, "TabBar immediate theme update")
        tab_node_path.write_text(tab_node, encoding="utf-8")

    # Preserve UIKit's trait propagation and ignore transient .unspecified style
    # values. Mapping .unspecified to .light during an iOS 27 transition can emit a
    # false light appearance in the middle of a dark/light switch.
    window_path = root / "submodules/Display/Source/NativeWindowHostView.swift"
    window = window_path.read_text(encoding="utf-8")
    if TRAIT_MARK not in window:
        old = '''    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {\n        if #available(iOS 12.0, *) {\n            self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: self.traitCollection.userInterfaceStyle))\n        }\n    }\n'''
        new = f'''    override func traitCollectionDidChange(_ previousTraitCollection: UITraitCollection?) {{\n        super.traitCollectionDidChange(previousTraitCollection)\n        if #available(iOS 12.0, *) {{\n            // {TRAIT_MARK}\n            let style = self.traitCollection.userInterfaceStyle\n            if style != .unspecified {{\n                self._systemUserInterfaceStyle.set(WindowUserInterfaceStyle(style: style))\n            }}\n        }}\n    }}\n'''
        window = one(window, old, new, "Window trait synchronization")
        window_path.write_text(window, encoding="utf-8")

    # The generic appearance bridge is inserted by apply_ayu_native_appearance_sync.
    # Move it before updateLegacyTheme(): legacy/native components should resolve
    # dynamic colors under the new trait rather than be corrected after rendering.
    shared_path = root / "submodules/TelegramUI/Sources/SharedAccountContext.swift"
    shared = shared_path.read_text(encoding="utf-8")
    if PRESENTATION_ORDER_MARK not in shared:
        old = '''                if themeUpdated {\n                    updateLegacyTheme()\n                    if #available(iOS 13.0, *) {\n                        ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.containerView, presentationData: next)\n                    }\n                    \n'''
        new = f'''                if themeUpdated {{\n                    // {PRESENTATION_ORDER_MARK}\n                    if #available(iOS 13.0, *) {{\n                        ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.containerView, presentationData: next)\n                    }}\n                    updateLegacyTheme()\n                    \n'''
        shared = one(shared, old, new, "appearance-before-legacy theme order")
        shared_path.write_text(shared, encoding="utf-8")

    # The actual visible root title is usually ChatListTitleView (NetworkStatusTitle),
    # which sits above the plain title. Brand the final value assigned to that view.
    chat_path = root / "submodules/ChatListUI/Sources/ChatListController.swift"
    chat = chat_path.read_text(encoding="utf-8")
    if CHAT_FINAL_MARK not in chat:
        old = '''            self.chatListTitle = titleContent\n'''
        new = f'''            // {CHAT_FINAL_MARK}\n            if case .chatList(.root) = self.location, !stateAndFilterId.state.editing, !titleContent.activity {{\n                titleContent.text = "AyuGram"\n            }}\n            self.chatListTitle = titleContent\n'''
        chat = one(chat, old, new, "final visible root chat-list title")
        chat_path.write_text(chat, encoding="utf-8")

    # Source-level verification. Swift/Bazel compilation remains the authoritative
    # build check in CI.
    lens_verify = lens_path.read_text(encoding="utf-8")
    if LENS_FALLBACK_MARK not in lens_verify or "majorVersion < 27" not in lens_verify:
        raise RuntimeError("iOS 27 private LiquidLens fallback missing")

    tab_verify = tab_path.read_text(encoding="utf-8")
    if TAB_REBUILD_MARK not in tab_verify:
        raise RuntimeError("TabBar theme rebuild missing")
    if "self.selectedItemViews.removeAll(keepingCapacity: true)" not in tab_verify:
        raise RuntimeError("selected TabBar item invalidation missing")
    if "self.liquidLensView.selectedContentView.overrideUserInterfaceStyle = ayuInterfaceStyle" not in tab_verify:
        raise RuntimeError("selected TabBar subtree appearance sync missing")

    tab_node_verify = tab_node_path.read_text(encoding="utf-8")
    if TAB_IMMEDIATE_MARK not in tab_node_verify or "self.updateImpl(params: layoutResult.params, transition: .immediate)" not in tab_node_verify:
        raise RuntimeError("immediate TabBar theme redraw missing")

    window_verify = window_path.read_text(encoding="utf-8")
    if TRAIT_MARK not in window_verify or "super.traitCollectionDidChange(previousTraitCollection)" not in window_verify:
        raise RuntimeError("window trait propagation fix missing")
    if "if style != .unspecified" not in window_verify:
        raise RuntimeError("transient unspecified appearance is not filtered")

    shared_verify = shared_path.read_text(encoding="utf-8")
    if PRESENTATION_ORDER_MARK not in shared_verify:
        raise RuntimeError("appearance sync is not ordered before legacy theme redraw")
    sync_index = shared_verify.find("ayuSyncNativeAppearance(view: strongSelf.mainWindow?.hostView.containerView")
    legacy_index = shared_verify.find("updateLegacyTheme()", sync_index)
    if sync_index < 0 or legacy_index < 0 or sync_index > legacy_index:
        raise RuntimeError("native appearance still updates after legacy theme rendering")

    chat_verify = chat_path.read_text(encoding="utf-8")
    if CHAT_FINAL_MARK not in chat_verify or 'titleContent.text = "AyuGram"' not in chat_verify:
        raise RuntimeError("final visible AyuGram title override missing")

    print("[ayu-ios27-render] early trait sync + private lens bypass + tab tint rebuild + final visible AyuGram title installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
