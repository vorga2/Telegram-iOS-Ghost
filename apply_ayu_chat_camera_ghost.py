#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


MARK = "AYU_CHAT_CAMERA_GHOST_v1"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def replace_range(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start anchor missing")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{label}: end anchor missing")
    if text.find(start, start_index + 1) >= 0:
        raise RuntimeError(f"{label}: duplicate start anchor")
    return text[:start_index] + replacement + text[end_index:]


def patch_runtime(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return

    text = one(
        text,
        "    case saveReadDates = 12\n}",
        "    case saveReadDates = 12\n"
        f"    // {MARK}\n"
        "    case rememberLastCamera = 13\n}",
        "camera runtime option",
    )
    text = one(
        text,
        "    public var saveReadDates: Bool\n    public var deletedMarkerStyle: Int32\n",
        "    public var saveReadDates: Bool\n    public var rememberLastCamera: Bool\n    public var deletedMarkerStyle: Int32\n",
        "camera snapshot field",
    )
    text = one(
        text,
        "        case .saveReadDates:\n            return keyPrefix + \"spy.saveReadDates\"\n        }",
        "        case .saveReadDates:\n            return keyPrefix + \"spy.saveReadDates\"\n"
        "        case .rememberLastCamera:\n            return keyPrefix + \"chats.camera.rememberLast\"\n        }",
        "camera key",
    )
    text = one(
        text,
        "        case .master:\n            return false\n        case .hideReadMessages",
        "        case .master, .rememberLastCamera:\n            return false\n        case .hideReadMessages",
        "camera default",
    )
    text = one(
        text,
        "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates:\n            break\n",
        "        case .onlinePulseOnSend, .keepDeletedMessages, .showDeletedMarker, .readOnActions, .useScheduled, .saveEditHistory, .saveReadDates, .rememberLastCamera:\n            break\n",
        "camera migration",
    )
    text = one(
        text,
        "            saveEditHistory: storedValue(.saveEditHistory, defaults: defaults),\n            saveReadDates: storedValue(.saveReadDates, defaults: defaults),\n            deletedMarkerStyle: style,",
        "            saveEditHistory: storedValue(.saveEditHistory, defaults: defaults),\n"
        "            saveReadDates: storedValue(.saveReadDates, defaults: defaults),\n"
        "            rememberLastCamera: storedValue(.rememberLastCamera, defaults: defaults),\n"
        "            deletedMarkerStyle: style,",
        "camera snapshot load",
    )
    text = one(
        text,
        "    private static let state = Atomic<AyuRuntimeSnapshot>(value: loadSnapshot())\n    private static let deletedState",
        "    private static let state = Atomic<AyuRuntimeSnapshot>(value: loadSnapshot())\n"
        "    private static let lastVideoMessageCameraKey = keyPrefix + \"chats.camera.lastIsFront\"\n"
        "    private static let lastVideoMessageCameraIsFront = Atomic<Bool>(value: UserDefaults.standard.object(forKey: lastVideoMessageCameraKey) == nil ? true : UserDefaults.standard.bool(forKey: lastVideoMessageCameraKey))\n"
        "    private static let deletedState",
        "camera memory state",
    )
    text = one(
        text,
        "        case .saveReadDates:\n            return current.saveReadDates\n        }\n    }",
        "        case .saveReadDates:\n            return current.saveReadDates\n"
        "        case .rememberLastCamera:\n            return current.rememberLastCamera\n"
        "        }\n    }",
        "camera value",
    )
    text = one(
        text,
        "            case .saveReadDates:\n                current.saveReadDates = value\n            }\n",
        "            case .saveReadDates:\n                current.saveReadDates = value\n"
        "            case .rememberLastCamera:\n                current.rememberLastCamera = value\n"
        "            }\n",
        "camera set",
    )
    anchor = "    public static func setDeletedMarkerStyle(_ value: Int32) {\n"
    helper = f'''    // {MARK}: read once when the round-video camera opens and write only
    // when Camera.position emits a real position change. No polling or frame work.
    public static var initialVideoMessageCameraIsFront: Bool {{
        guard snapshot.rememberLastCamera else {{
            return true
        }}
        return lastVideoMessageCameraIsFront.with {{ $0 }}
    }}

    public static func recordVideoMessageCameraIsFront(_ value: Bool) {{
        guard snapshot.rememberLastCamera else {{
            return
        }}
        let previous = lastVideoMessageCameraIsFront.swap(value)
        if previous != value {{
            UserDefaults.standard.set(value, forKey: lastVideoMessageCameraKey)
        }}
    }}

'''
    text = one(text, anchor, helper + anchor, "camera helpers")
    path.write_text(text, encoding="utf-8")


def patch_camera(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return
    text = one(
        text,
        "            let isFrontPosition = \"\".isEmpty\n",
        f"            // {MARK}: stock default is front; use the saved position only when enabled.\n"
        "            let isFrontPosition = AyuRuntimeSettings.initialVideoMessageCameraIsFront\n",
        "camera initial position",
    )
    text = one(
        text,
        "                self.cameraState = self.cameraState.updatedPosition(position).updatedFlashMode(flashMode)\n                \n                if !self.cameraState.isDualCameraEnabled {",
        "                self.cameraState = self.cameraState.updatedPosition(position).updatedFlashMode(flashMode)\n"
        "                AyuRuntimeSettings.recordVideoMessageCameraIsFront(position == .front)\n"
        "                \n                if !self.cameraState.isDualCameraEnabled {",
        "camera position event",
    )
    path.write_text(text, encoding="utf-8")


GHOST_BLOCK = r'''// AYU_CHAT_CAMERA_GHOST_v1: native expandable Ghost row.
private final class AyuGhostArguments {
    let updateBool: (AyuRuntimeOption, Bool) -> Void
    let toggleExpanded: () -> Void

    init(updateBool: @escaping (AyuRuntimeOption, Bool) -> Void, toggleExpanded: @escaping () -> Void) {
        self.updateBool = updateBool
        self.toggleExpanded = toggleExpanded
    }
}

private enum AyuGhostSection: Int32 { case ghost }

private enum AyuGhostEntry: ItemListNodeEntry {
    case header
    case ghost(Bool, Bool, [ItemListExpandableSwitchItem.SubItem])

    var section: ItemListSectionId { AyuGhostSection.ghost.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .ghost: return 1
        }
    }
    static func <(lhs: AyuGhostEntry, rhs: AyuGhostEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuGhostArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "РЕЖИМ ПРИЗРАКА", sectionId: self.section)
        case let .ghost(value, isExpanded, subItems):
            return ItemListExpandableSwitchItem(
                presentationData: presentationData,
                systemStyle: .glass,
                title: "Режим призрака",
                value: value,
                isExpanded: isExpanded,
                subItems: subItems,
                sectionId: self.section,
                style: .blocks,
                updated: { arguments.updateBool(.master, $0) },
                selectAction: { arguments.toggleExpanded() },
                subAction: { subItem in
                    if subItem.id == AnyHashable("read") { arguments.updateBool(.hideReadMessages, !subItem.isSelected) }
                    else if subItem.id == AnyHashable("stories") { arguments.updateBool(.hideReadStories, !subItem.isSelected) }
                    else if subItem.id == AnyHashable("online") { arguments.updateBool(.hideOnline, !subItem.isSelected) }
                    else if subItem.id == AnyHashable("typing") { arguments.updateBool(.hideTyping, !subItem.isSelected) }
                    else if subItem.id == AnyHashable("offline") { arguments.updateBool(.automaticOffline, !subItem.isSelected) }
                    else if subItem.id == AnyHashable("actions") { arguments.updateBool(.readOnActions, !subItem.isSelected) }
                    else if subItem.id == AnyHashable("scheduled") { arguments.updateBool(.useScheduled, !subItem.isSelected) }
                }
            )
        }
    }
}

private func ayuGhostEntries(_ snapshot: AyuRuntimeSnapshot, isExpanded: Bool) -> [AyuGhostEntry] {
    let subItems: [ItemListExpandableSwitchItem.SubItem] = [
        .init(id: AnyHashable("read"), title: "Не читать сообщения", isSelected: snapshot.hideReadMessages, isEnabled: true),
        .init(id: AnyHashable("stories"), title: "Не отмечать просмотр историй", isSelected: snapshot.hideReadStories, isEnabled: true),
        .init(id: AnyHashable("online"), title: "Скрывать онлайн", isSelected: snapshot.hideOnline, isEnabled: true),
        .init(id: AnyHashable("typing"), title: "Скрывать «печатает…»", isSelected: snapshot.hideTyping, isEnabled: true),
        .init(id: AnyHashable("offline"), title: "Автоматически офлайн", isSelected: snapshot.automaticOffline, isEnabled: true),
        .init(id: AnyHashable("actions"), title: "Читать при действиях", isSelected: snapshot.readOnActions, isEnabled: true),
        .init(id: AnyHashable("scheduled"), title: "Использовать отложку", isSelected: snapshot.useScheduled, isEnabled: true)
    ]
    return [.header, .ghost(snapshot.master, isExpanded, subItems)]
}

'''


GHOST_CONTROLLER = r'''private func ayuGhostSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let bump: () -> Void = { revisionValue &+= 1; revision.set(revisionValue) }
    let expanded = ValuePromise<Bool>(false, ignoreRepeated: true)
    var expandedValue = false
    let arguments = AyuGhostArguments(updateBool: { option, value in
        AyuRuntimeSettings.set(option, value: value)
        switch option {
        case .master, .hideOnline:
            ayuApplyGhostPresence(account: context.account)
        default:
            break
        }
        bump()
    }, toggleExpanded: {
        expandedValue = !expandedValue
        expanded.set(expandedValue)
    })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get(), expanded.get())
    |> deliverOnMainQueue
    |> map { presentationData, _, isExpanded -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Режим Призрака"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: ayuGhostEntries(AyuRuntimeSettings.snapshot, isExpanded: isExpanded), style: .blocks, animateChanges: true), arguments))
    }
    return ItemListController(context: context, state: signal)
}

'''


CHATS_CONTROLLER = r'''// AYU_CHAT_CAMERA_GHOST_v1: Chats -> Camera settings.
private final class AyuChatsArguments {
    let updateRememberCamera: (Bool) -> Void
    init(updateRememberCamera: @escaping (Bool) -> Void) {
        self.updateRememberCamera = updateRememberCamera
    }
}

private enum AyuChatsSection: Int32 { case camera }

private enum AyuChatsEntry: ItemListNodeEntry {
    case header
    case rememberLastCamera(Bool)

    var section: ItemListSectionId { AyuChatsSection.camera.rawValue }
    var stableId: Int32 {
        switch self {
        case .header: return 0
        case .rememberLastCamera: return 1
        }
    }
    static func <(lhs: AyuChatsEntry, rhs: AyuChatsEntry) -> Bool { lhs.stableId < rhs.stableId }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let arguments = arguments as! AyuChatsArguments
        switch self {
        case .header:
            return ItemListSectionHeaderItem(presentationData: presentationData, text: "КАМЕРА", sectionId: self.section)
        case let .rememberLastCamera(value):
            return ItemListSwitchItem(presentationData: presentationData, systemStyle: .glass, title: "Запоминать последнюю камеру", value: value, sectionId: self.section, style: .blocks, updated: arguments.updateRememberCamera)
        }
    }
}

private func ayuChatsSettingsController(context: AccountContext) -> ViewController {
    let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    var revisionValue: Int32 = 0
    let arguments = AyuChatsArguments(updateRememberCamera: { value in
        AyuRuntimeSettings.set(.rememberLastCamera, value: value)
        revisionValue &+= 1
        revision.set(revisionValue)
    })
    let signal = combineLatest(context.sharedContext.presentationData, revision.get())
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries: [AyuChatsEntry] = [.header, .rememberLastCamera(AyuRuntimeSettings.snapshot.rememberLastCamera)]
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Чаты"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        return (controllerState, (ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: true), arguments))
    }
    return ItemListController(context: context, state: signal)
}

'''


def patch_settings(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARK in text:
        return

    text = replace_range(
        text,
        "private final class AyuGhostArguments {",
        "private final class AyuCustomizationArguments {",
        GHOST_BLOCK,
        "expandable ghost block",
    )
    text = replace_range(
        text,
        "private func ayuGhostSettingsController(context: AccountContext) -> ViewController {",
        "func ayuSettingsController(context: AccountContext) -> ViewController {",
        GHOST_CONTROLLER + CHATS_CONTROLLER,
        "expandable ghost controller",
    )
    text = one(
        text,
        "    let openCustomization: () -> Void\n    let openSpy: () -> Void\n\n    init(openGhost: @escaping () -> Void, openCustomization: @escaping () -> Void, openSpy: @escaping () -> Void) {\n        self.openGhost = openGhost\n        self.openCustomization = openCustomization\n        self.openSpy = openSpy\n",
        "    let openCustomization: () -> Void\n"
        "    let openSpy: () -> Void\n"
        "    let openChats: () -> Void\n\n"
        "    init(openGhost: @escaping () -> Void, openCustomization: @escaping () -> Void, openSpy: @escaping () -> Void, openChats: @escaping () -> Void) {\n"
        "        self.openGhost = openGhost\n"
        "        self.openCustomization = openCustomization\n"
        "        self.openSpy = openSpy\n"
        "        self.openChats = openChats\n",
        "chats main arguments",
    )
    text = one(
        text,
        "    case customization\n    case spy\n",
        "    case customization\n    case spy\n    case chats\n",
        "chats main entry",
    )
    text = one(
        text,
        "        case .spy: return 3\n",
        "        case .spy: return 3\n        case .chats: return 4\n",
        "chats stable id",
    )
    text = one(
        text,
        "        case .spy:\n            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: \"Шпион\", label: \"\", sectionId: self.section, style: .blocks, action: { arguments.openSpy() })\n",
        "        case .spy:\n"
        "            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: \"Шпион\", label: \"\", sectionId: self.section, style: .blocks, action: { arguments.openSpy() })\n"
        "        case .chats:\n"
        "            return ItemListDisclosureItem(presentationData: presentationData, systemStyle: .glass, title: \"Чаты\", label: \"\", sectionId: self.section, style: .blocks, action: { arguments.openChats() })\n",
        "chats main row",
    )
    text = one(
        text,
        "    }, openSpy: {\n        controllerBox.value?.push(ayuSpySettingsController(context: context))\n    })",
        "    }, openSpy: {\n"
        "        controllerBox.value?.push(ayuSpySettingsController(context: context))\n"
        "    }, openChats: {\n"
        "        controllerBox.value?.push(ayuChatsSettingsController(context: context))\n"
        "    })",
        "chats navigation",
    )
    text = one(
        text,
        "        let entries: [AyuMainEntry] = [.header, .ghost, .customization, .spy]\n",
        "        let entries: [AyuMainEntry] = [.header, .ghost, .customization, .spy, .chats]\n",
        "chats root entries",
    )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_chat_camera_ghost.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    patch_runtime(root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift")
    patch_camera(root / "submodules/TelegramUI/Components/VideoMessageCameraScreen/Sources/VideoMessageCameraScreen.swift")
    patch_settings(root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift")

    runtime = (root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift").read_text(encoding="utf-8")
    camera = (root / "submodules/TelegramUI/Components/VideoMessageCameraScreen/Sources/VideoMessageCameraScreen.swift").read_text(encoding="utf-8")
    settings = (root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift").read_text(encoding="utf-8")
    checks = (
        (runtime, "case rememberLastCamera = 13"),
        (runtime, "initialVideoMessageCameraIsFront"),
        (camera, "recordVideoMessageCameraIsFront(position == .front)"),
        (settings, "ItemListExpandableSwitchItem("),
        (settings, 'title: "Запоминать последнюю камеру"'),
        (settings, 'title: "Чаты"'),
    )
    for source, value in checks:
        if value not in source:
            raise RuntimeError(f"chat/camera/Ghost patch incomplete: {value}")

    print("[ayu-chat-camera-ghost] Chats camera memory + expandable Ghost installed without polling")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
