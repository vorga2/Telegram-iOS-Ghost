#!/usr/bin/env python3
from pathlib import Path
import sys

import apply_ayu_deleted_visual_compile_fix as visual_compile_fix

MARK = "AYU_CUSTOMIZATION_FINISH_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_customization_finish.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    text = runtime.read_text(encoding="utf-8")
    if MARK not in text:
        text = one(
            text,
            "    case saveReadDates = 12\n}",
            "    case saveReadDates = 12\n    // AYU_CUSTOMIZATION_FINISH_v0_3\n    case translucentDeleted = 13\n}",
            "customization runtime option",
        )
        text = one(
            text,
            "    public var saveReadDates: Bool\n    public var deletedMarkerStyle: Int32\n",
            "    public var saveReadDates: Bool\n    public var translucentDeleted: Bool\n    public var deletedMarkerStyle: Int32\n",
            "customization snapshot field",
        )
        text = one(
            text,
            "        case .saveReadDates:\n            return keyPrefix + \"spy.saveReadDates\"\n        }",
            "        case .saveReadDates:\n            return keyPrefix + \"spy.saveReadDates\"\n        case .translucentDeleted:\n            return keyPrefix + \"customization.translucentDeleted\"\n        }",
            "customization key",
        )
        text = one(
            text,
            "        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates:\n            return true\n",
            "        case .hideReadMessages, .hideReadStories, .hideOnline, .hideTyping, .automaticOffline, .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates, .translucentDeleted:\n            return true\n",
            "customization default",
        )
        text = one(
            text,
            "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates:\n            break\n",
            "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates, .translucentDeleted:\n            break\n",
            "customization migration",
        )
        text = one(
            text,
            "            saveEditHistory: storedValue(.saveEditHistory, defaults: defaults),\n            saveReadDates: storedValue(.saveReadDates, defaults: defaults),\n            deletedMarkerStyle: style,",
            "            saveEditHistory: storedValue(.saveEditHistory, defaults: defaults),\n            saveReadDates: storedValue(.saveReadDates, defaults: defaults),\n            translucentDeleted: storedValue(.translucentDeleted, defaults: defaults),\n            deletedMarkerStyle: style,",
            "customization load",
        )
        text = one(
            text,
            "        case .saveReadDates:\n            return current.saveReadDates\n        }\n    }",
            "        case .saveReadDates:\n            return current.saveReadDates\n        case .translucentDeleted:\n            return current.translucentDeleted\n        }\n    }",
            "customization value",
        )
        text = one(
            text,
            "            case .saveReadDates:\n                current.saveReadDates = value\n            }\n",
            "            case .saveReadDates:\n                current.saveReadDates = value\n            case .translucentDeleted:\n                current.translucentDeleted = value\n            }\n",
            "customization set",
        )
    runtime.write_text(text, encoding="utf-8")

    # Point 7: the full-message 0.5 alpha is user-controllable and defaults ON.
    message_item = root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift"
    text = message_item.read_text(encoding="utf-8")
    text = text.replace(
        "let ayuDeletedWholeItem = AyuRuntimeSettings.isDeleted(self.message.id) && !AyuRuntimeSettings.isInDeletedViewer(self.message.id)",
        "let ayuDeletedWholeItem = AyuRuntimeSettings.snapshot.translucentDeleted && AyuRuntimeSettings.isDeleted(self.message.id) && !AyuRuntimeSettings.isInDeletedViewer(self.message.id)",
    )
    message_item.write_text(text, encoding="utf-8")

    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    text = settings.read_text(encoding="utf-8")
    if MARK not in text:
        # Saving deleted messages belongs to Spy now, so remove the duplicate row
        # from Customization and use that slot for the requested translucency toggle.
        text = one(
            text,
            "    case keepDeleted(Bool)\n    case showMarker(Bool)\n",
            "    // AYU_CUSTOMIZATION_FINISH_v0_3\n    case translucentDeleted(Bool)\n    case showMarker(Bool)\n",
            "customization entry case",
        )
        text = one(
            text,
            "        case .keepDeleted: return 1\n        case .showMarker: return 2\n",
            "        case .translucentDeleted: return 1\n        case .showMarker: return 2\n",
            "customization stable id",
        )
        text = one(
            text,
            "        case let .keepDeleted(value):\n            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: \"Сохранять удалённые сообщения\", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.keepDeletedMessages, $0) })\n",
            "        case let .translucentDeleted(value):\n            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: \"Полупрозрачные удаленки\", value: value, sectionId: self.section, style: .blocks, updated: { arguments.updateBool(.translucentDeleted, $0) })\n",
            "customization translucency row",
        )

        # Marker picker: icon-only options and icon-only preview. Blank means no
        # marker glyph. Keep the independent showMarker switch as the global on/off.
        old_options = '        let options: [(AyuDeletedMarkerStyle, String)] = [(.text, "Убрать значок"), (.trash, "👀"), (.cross, "❌"), (.compact, "👀")]\n'
        new_options = '        let options: [(AyuDeletedMarkerStyle, String)] = [(.text, " "), (.trash, "👀"), (.cross, "❌")]\n'
        text = one(text, old_options, new_options, "icon-only marker picker")

        text = one(
            text,
            "        let entries: [AyuCustomizationEntry] = [.header, .keepDeleted(snapshot.keepDeletedMessages), .showMarker(snapshot.showDeletedMarker), .markerStyle(AyuRuntimeSettings.deletedMarkerStyleTitle), .markerColor(AyuRuntimeSettings.deletedMarkerColorTitle), .clearDeleted]",
            "        let ayuMarkerPreview = snapshot.showDeletedMarker ? AyuRuntimeSettings.deletedMarkerPrefix : \"\"\n        let entries: [AyuCustomizationEntry] = [.header, .translucentDeleted(snapshot.translucentDeleted), .showMarker(snapshot.showDeletedMarker), .markerStyle(ayuMarkerPreview), .markerColor(AyuRuntimeSettings.deletedMarkerColorTitle), .clearDeleted]",
            "icon-only marker preview",
        )
    settings.write_text(text, encoding="utf-8")

    # The visual hotfix used to keep a temporary per-bubble Telegram-theme flag.
    # Whole-message opacity superseded it, leaving a write-only Swift local that
    # fails Telegram's warnings-as-errors build. Remove it in both verification
    # and the real IPA pipeline so they compile the same final source.
    visual_compile_fix.main()

    print("[ayu-customization-finish] translucent deleted toggle + icon-only marker picker installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
