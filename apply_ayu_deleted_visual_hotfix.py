#!/usr/bin/env python3
from pathlib import Path
import sys


def one(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_visual_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()

    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    t = runtime.read_text(encoding="utf-8")
    if "case telegram = 8" not in t:
        t = one(t, "    case blue = 7\n}\n", "    case blue = 7\n    case telegram = 8\n}\n", "telegram color enum")
        t = one(t, "            color = AyuDeletedMarkerColor.red.rawValue\n", "            color = AyuDeletedMarkerColor.telegram.rawValue\n", "telegram default")
        t = one(t, "let normalized = AyuDeletedMarkerColor(rawValue: value)?.rawValue ?? AyuDeletedMarkerColor.red.rawValue", "let normalized = AyuDeletedMarkerColor(rawValue: value)?.rawValue ?? AyuDeletedMarkerColor.telegram.rawValue", "telegram fallback")
        t = one(t, "        case .blue:\n            return \"Синий\"\n        }\n    }\n", "        case .blue:\n            return \"Синий\"\n        case .telegram:\n            return \"Тема Telegram\"\n        }\n    }\n", "telegram title")
    runtime.write_text(t, encoding="utf-8")

    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    t = settings.read_text(encoding="utf-8")
    t = t.replace("let current = AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .red", "let current = AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .telegram")
    options_anchor = "        let options: [(AyuDeletedMarkerColor, String)] = [\n"
    if "(.telegram, \"Тема Telegram\")" not in t:
        t = one(t, options_anchor, options_anchor + "            (.telegram, \"Тема Telegram\"),\n", "telegram option")
    settings.write_text(t, encoding="utf-8")

    # Restore deletion icons without touching Telegram's date/status layout code.
    timestamp = root / "submodules/TelegramUI/Components/Chat/ChatMessageDateAndStatusNode/Sources/StringForMessageTimestampStatus.swift"
    t = timestamp.read_text(encoding="utf-8")
    if "decorateTimestamp(dateText" not in t:
        t = one(t, "    return dateText\n}\n", "    return AyuRuntimeSettings.decorateTimestamp(dateText, messageId: message.id)\n}\n", "deleted timestamp marker")
    timestamp.write_text(t, encoding="utf-8")

    bubble = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    t = bubble.read_text(encoding="utf-8")
    old = '''        let ayuDeletedBackgroundColor: UIColor?\n        if AyuRuntimeSettings.isDeleted(item.message.id) && !AyuRuntimeSettings.isInDeletedViewer(item.message.id) {\n            let baseColor: UIColor\n            switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .red {\n            case .red:\n                baseColor = UIColor.systemRed\n            case .orange:\n                baseColor = UIColor.systemOrange\n            case .gray:\n                baseColor = UIColor.systemGray\n            case .purple:\n                baseColor = UIColor.systemPurple\n            case .pink:\n                baseColor = UIColor.systemPink\n            case .magenta:\n                baseColor = UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: 1.0)\n            case .indigo:\n                baseColor = UIColor.systemIndigo\n            case .blue:\n                baseColor = UIColor.systemBlue\n            }\n            ayuDeletedBackgroundColor = baseColor.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n        } else {\n            ayuDeletedBackgroundColor = nil\n        }\n        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n\n        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: ayuBackgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n'''
    new = '''        let ayuDeletedBackgroundColor: UIColor?\n        let ayuUsesTelegramTheme: Bool\n        if AyuRuntimeSettings.isDeleted(item.message.id) && !AyuRuntimeSettings.isInDeletedViewer(item.message.id) {\n            switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .telegram {\n            case .telegram:\n                ayuDeletedBackgroundColor = nil\n                ayuUsesTelegramTheme = true\n            case .red:\n                ayuDeletedBackgroundColor = UIColor.systemRed.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .orange:\n                ayuDeletedBackgroundColor = UIColor.systemOrange.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .gray:\n                ayuDeletedBackgroundColor = UIColor.systemGray.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .purple:\n                ayuDeletedBackgroundColor = UIColor.systemPurple.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .pink:\n                ayuDeletedBackgroundColor = UIColor.systemPink.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .magenta:\n                ayuDeletedBackgroundColor = UIColor(red: 0.86, green: 0.12, blue: 0.46, alpha: CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .indigo:\n                ayuDeletedBackgroundColor = UIColor.systemIndigo.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            case .blue:\n                ayuDeletedBackgroundColor = UIColor.systemBlue.withAlphaComponent(CGFloat(AyuRuntimeSettings.deletedMessageAlpha))\n                ayuUsesTelegramTheme = false\n            }\n        } else {\n            ayuDeletedBackgroundColor = nil\n            ayuUsesTelegramTheme = false\n        }\n        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n        strongSelf.backgroundNode.alpha = ayuUsesTelegramTheme ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n        strongSelf.backgroundWallpaperNode.alpha = ayuUsesTelegramTheme ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n\n        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: ayuBackgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n'''
    if "ayuUsesTelegramTheme" not in t:
        t = one(t, old, new, "Telegram-theme deleted bubble")
    bubble.write_text(t, encoding="utf-8")

    print("[ayu-deleted-visual-hotfix] marker restored; default background follows Telegram theme")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
