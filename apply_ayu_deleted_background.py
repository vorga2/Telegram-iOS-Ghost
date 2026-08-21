#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_DELETED_DARK_BUBBLE_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_background.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    text = path.read_text(encoding="utf-8")

    if MARK not in text:
        text = one(
            text,
            "    private let backgroundNode: ChatMessageBackground\n    private var backgroundHighlightNode: ChatMessageBackground?\n",
            "    private let backgroundNode: ChatMessageBackground\n"
            f"    // {MARK}: a deleted-only tint layer, masked with Telegram's own bubble image.\n"
            "    private let ayuDeletedBackgroundNode: ASImageNode\n"
            "    private var backgroundHighlightNode: ChatMessageBackground?\n",
            "deleted bubble property",
        )
        text = one(
            text,
            "        self.backgroundNode = ChatMessageBackground()\n        self.backgroundNode.backdropNode = self.backgroundWallpaperNode\n        self.shadowNode = ChatMessageShadowNode()\n",
            "        self.backgroundNode = ChatMessageBackground()\n"
            "        self.backgroundNode.backdropNode = self.backgroundWallpaperNode\n"
            "        self.ayuDeletedBackgroundNode = ASImageNode()\n"
            "        self.ayuDeletedBackgroundNode.displaysAsynchronously = false\n"
            "        self.ayuDeletedBackgroundNode.displayWithoutProcessing = true\n"
            "        self.ayuDeletedBackgroundNode.isUserInteractionEnabled = false\n"
            "        self.ayuDeletedBackgroundNode.isHidden = true\n"
            "        self.shadowNode = ChatMessageShadowNode()\n",
            "deleted bubble init",
        )
        text = one(
            text,
            "        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundWallpaperNode)\n        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundNode)\n        self.mainContextSourceNode.contentNode.addSubnode(self.clippingNode)\n",
            "        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundWallpaperNode)\n"
            "        self.mainContextSourceNode.contentNode.addSubnode(self.backgroundNode)\n"
            "        self.mainContextSourceNode.contentNode.addSubnode(self.ayuDeletedBackgroundNode)\n"
            "        self.mainContextSourceNode.contentNode.addSubnode(self.clippingNode)\n",
            "deleted bubble hierarchy",
        )
        anchor = (
            "        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: strongSelf.backgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n"
            "        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n"
            "        strongSelf.shadowNode.setType(type: backgroundType, hasWallpaper: hasWallpaper, graphics: graphics)\n"
        )
        replacement = anchor + f'''        // {MARK}: only dark-theme deleted bubbles receive the chosen custom
        // background. Incoming and outgoing use the same selected color. The
        // final message node already has alpha 0.5, so this layer stays opaque
        // and the effective bubble opacity is exactly 0.5 (not 0.25).
        let ayuDeletedBubbleColor: UIColor?
        if item.presentationData.theme.theme.overallDarkAppearance,
           AyuRuntimeSettings.isDeleted(item.message.id),
           !AyuRuntimeSettings.isInDeletedViewer(item.message.id) {{
            switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .telegram {{
            case .red: ayuDeletedBubbleColor = UIColor.systemRed
            case .orange: ayuDeletedBubbleColor = UIColor.systemOrange
            case .gray: ayuDeletedBubbleColor = UIColor.systemGray
            case .purple: ayuDeletedBubbleColor = UIColor.systemPurple
            case .pink: ayuDeletedBubbleColor = UIColor.systemPink
            case .magenta: ayuDeletedBubbleColor = UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: 1.0)
            case .indigo: ayuDeletedBubbleColor = UIColor.systemIndigo
            case .blue: ayuDeletedBubbleColor = UIColor.systemBlue
            case .telegram: ayuDeletedBubbleColor = nil
            }}
        }} else {{
            ayuDeletedBubbleColor = nil
        }}
        if let ayuDeletedBubbleColor,
           let maskImage = bubbleMaskForType(backgroundType, graphics: graphics),
           let tintedImage = generateTintedImage(image: maskImage, color: ayuDeletedBubbleColor) {{
            strongSelf.ayuDeletedBackgroundNode.image = tintedImage.resizableImage(withCapInsets: maskImage.capInsets, resizingMode: maskImage.resizingMode)
            strongSelf.ayuDeletedBackgroundNode.isHidden = false
        }} else {{
            strongSelf.ayuDeletedBackgroundNode.image = nil
            strongSelf.ayuDeletedBackgroundNode.isHidden = true
        }}
        animation.animator.updateFrame(layer: strongSelf.ayuDeletedBackgroundNode.layer, frame: backgroundFrame, completion: nil)
'''
        text = one(text, anchor, replacement, "deleted bubble render")
        path.write_text(text, encoding="utf-8")

    verify = path.read_text(encoding="utf-8")
    required = (
        MARK,
        "private let ayuDeletedBackgroundNode: ASImageNode",
        "bubbleMaskForType(backgroundType, graphics: graphics)",
        "theme.overallDarkAppearance",
        "case .telegram: ayuDeletedBubbleColor = nil",
    )
    for value in required:
        if value not in verify:
            raise RuntimeError(f"deleted dark bubble incomplete: {value}")

    print("[ayu-deleted-background] dark deleted bubbles use the selected color at effective alpha 0.5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
