#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"{label}: anchor not found")
    return text.replace(old, new, 1)


def patch_background(path: Path) -> None:
    text = path.read_text()

    old_props = """    public var customHighlightColor: UIColor? {\n        didSet {\n            self.imageView?.tintColor = self.customHighlightColor\n        }\n    }\n\n    public var backgroundFrame: CGRect = .zero\n"""
    new_props = """    public var customHighlightColor: UIColor? {\n        didSet {\n            self.imageView?.tintColor = self.customHighlightColor\n        }\n    }\n\n    // AYU_IOS_PATCH_v0_3: optional deleted-message bubble fill.\n    // Images are cached by source bubble image + color, so scrolling does not\n    // regenerate bubble assets or allocate a new rendered image per frame.\n    public var ayuCustomFillColor: UIColor?\n    private var ayuAppliedCustomFillColor: UIColor?\n    private static let ayuFillImageCache = NSCache<NSString, UIImage>()\n\n    private static func ayuFillImage(_ image: UIImage, color: UIColor) -> UIImage {\n        let key = \"\\(ObjectIdentifier(image).hashValue):\\(color.hash)\" as NSString\n        if let cached = self.ayuFillImageCache.object(forKey: key) {\n            return cached\n        }\n        let tinted = image.withTintColor(color, renderingMode: .alwaysOriginal)\n        let result: UIImage\n        if image.capInsets == .zero {\n            result = tinted\n        } else {\n            result = tinted.resizableImage(withCapInsets: image.capInsets, resizingMode: image.resizingMode)\n        }\n        self.ayuFillImageCache.setObject(result, forKey: key)\n        return result\n    }\n\n    public var backgroundFrame: CGRect = .zero\n"""
    text = replace_once(text, old_props, new_props, "deleted-bg-properties")

    old_fast_path = """        let previousType = self.type\n        if let currentType = previousType, currentType == type, self.currentHighlighted == highlighted, self.graphics === graphics, backgroundNode === self.backgroundNode, self.maskMode == maskMode, self.hasWallpaper == hasWallpaper {\n            return\n        }\n        self.type = type\n"""
    new_fast_path = """        let previousType = self.type\n        let sameAyuFill: Bool\n        if let lhs = self.ayuAppliedCustomFillColor, let rhs = self.ayuCustomFillColor {\n            sameAyuFill = lhs.isEqual(rhs)\n        } else {\n            sameAyuFill = self.ayuAppliedCustomFillColor == nil && self.ayuCustomFillColor == nil\n        }\n        if let currentType = previousType, currentType == type, self.currentHighlighted == highlighted, self.graphics === graphics, backgroundNode === self.backgroundNode, self.maskMode == maskMode, self.hasWallpaper == hasWallpaper, sameAyuFill {\n            return\n        }\n        self.ayuAppliedCustomFillColor = self.ayuCustomFillColor\n        self.type = type\n"""
    text = replace_once(text, old_fast_path, new_fast_path, "deleted-bg-fast-path")

    old_outline_anchor = """        let outlineImage: UIImage?\n"""
    new_outline_anchor = """        if !highlighted, let ayuCustomFillColor = self.ayuCustomFillColor, let currentImage = image {\n            image = Self.ayuFillImage(currentImage, color: ayuCustomFillColor)\n        }\n\n        let outlineImage: UIImage?\n"""
    text = replace_once(text, old_outline_anchor, new_outline_anchor, "deleted-bg-tint")

    path.write_text(text)


def patch_bubble_node(path: Path) -> None:
    text = path.read_text()

    old = """        let hasWallpaper = item.presentationData.theme.wallpaper.hasWallpaper\n        if item.presentationData.theme.theme.forceSync {\n            legacyTransition = .immediate\n        }\n        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: strongSelf.backgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n"""
    new = """        let hasWallpaper = item.presentationData.theme.wallpaper.hasWallpaper\n        if item.presentationData.theme.theme.forceSync {\n            legacyTransition = .immediate\n        }\n\n        // AYU_IOS_PATCH_v0_3: the deleted-message color setting now controls the\n        // stock Telegram bubble background instead of recoloring timestamp/marker text.\n        // This is only an O(1) Atomic lookup + enum switch during normal item layout.\n        let ayuDeletedBackgroundColor: UIColor?\n        if AyuRuntimeSettings.isDeleted(item.message.id) {\n            switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .red {\n            case .red:\n                ayuDeletedBackgroundColor = UIColor.systemRed\n            case .orange:\n                ayuDeletedBackgroundColor = UIColor.systemOrange\n            case .gray:\n                ayuDeletedBackgroundColor = UIColor.systemGray\n            case .purple:\n                ayuDeletedBackgroundColor = UIColor.systemPurple\n            case .pink:\n                ayuDeletedBackgroundColor = UIColor.systemPink\n            case .magenta:\n                ayuDeletedBackgroundColor = UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: 1.0)\n            case .indigo:\n                ayuDeletedBackgroundColor = UIColor.systemIndigo\n            case .blue:\n                ayuDeletedBackgroundColor = UIColor.systemBlue\n            }\n        } else {\n            ayuDeletedBackgroundColor = nil\n        }\n        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n\n        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: ayuBackgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n"""
    text = replace_once(text, old, new, "deleted-bg-bubble-node")
    path.write_text(text)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_background.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_background(root / "submodules/ChatMessageBackground/Sources/ChatMessageBackground.swift")
    patch_bubble_node(root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift")
    print("Ayu deleted-message background patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
