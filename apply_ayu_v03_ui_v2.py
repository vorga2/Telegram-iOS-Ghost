#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

import apply_ayu_v03_crashfix as crashfix

base = crashfix.base


def patch_read_state(text: str) -> str:
    """Keep the transaction-safe Ghost read suppression, but allow exactly one
    explicit read synchronization when the user taps the Ayu 'Прочитать' action.
    """
    old = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""

    new = """func synchronizePeerReadState(network: Network, postbox: Postbox, stateManager: AccountStateManager, peerId: PeerId, push: Bool, validate: Bool) -> Signal<Never, PeerReadStateValidationError> {\n    // AYU_IOS_PATCH_v0_3: Ghost read suppression must remove the Postbox\n    // synchronization operation before completing. Returning .single(readState)\n    // here/inside pushPeerReadState completes synchronously while the operation is\n    // still visible, and ManagedSynchronizePeerReadStates immediately calls update()\n    // again -> unbounded SwiftSignalKit recursion / stack overflow.\n    if AyuRuntimeSettings.shouldSuppressRead(peerId: peerId) {\n        return postbox.transaction { transaction -> Void in\n            transaction.confirmSynchronizedIncomingReadState(peerId)\n        }\n        |> castError(PeerReadStateValidationError.self)\n        |> ignoreValues\n    }\n\n    // A manual allowance is single-use: this synchronization is allowed through,\n    // then Ghost immediately resumes suppressing future read receipts.\n    AyuRuntimeSettings.consumeManualReadAllowance(peerId: peerId)\n\n    var signal: Signal<Never, PeerReadStateValidationError> = .complete()\n    if push {\n        signal = signal\n        |> then(pushPeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    if validate {\n        signal = signal\n        |> then(validatePeerReadState(network: network, postbox: postbox, stateManager: stateManager, peerId: peerId))\n    }\n    return signal\n}"""

    return base.replace_once(text, old, new, "read-crashfix-manual-bypass")


def patch_status_marker_only(text: str) -> str:
    """Tint only the deletion marker. The actual message time keeps Telegram's
    original secondary-text color, fixing the old behavior that colored the date.
    """
    old = """            let dateFont = Font.regular(floor(arguments.presentationData.fontSize.baseDisplaySize * 11.0 / 17.0))\n            let (date, dateApply) = dateLayout(TextNodeLayoutArguments(attributedString: NSAttributedString(string: updatedDateText, font: dateFont, textColor: dateColor), backgroundColor: nil, maximumNumberOfLines: 1, truncationType: .middle, constrainedSize: arguments.constrainedSize, alignment: .natural, cutout: nil, insets: UIEdgeInsets()))\n"""
    new = """            let dateFont = Font.regular(floor(arguments.presentationData.fontSize.baseDisplaySize * 11.0 / 17.0))\n            // AYU_IOS_PATCH_v0_3: keep Telegram's normal date color. Only the\n            // deletion marker prefix is tinted with the selected Ayu color.\n            let ayuDateText = NSMutableAttributedString(string: updatedDateText, font: dateFont, textColor: dateColor)\n            if AyuRuntimeSettings.isDeletedTimestampText(updatedDateText) {\n                let markerPrefix = AyuRuntimeSettings.deletedMarkerPrefix + \" \"\n                let markerLength = (markerPrefix as NSString).length\n                if markerLength <= ayuDateText.length {\n                    let markerColor: UIColor\n                    switch AyuDeletedMarkerColor(rawValue: AyuRuntimeSettings.snapshot.deletedMarkerColor) ?? .red {\n                    case .red:\n                        markerColor = UIColor.systemRed\n                    case .orange:\n                        markerColor = UIColor.systemOrange\n                    case .gray:\n                        markerColor = UIColor.systemGray\n                    case .purple:\n                        markerColor = UIColor.systemPurple\n                    }\n                    ayuDateText.addAttribute(.foregroundColor, value: markerColor, range: NSRange(location: 0, length: markerLength))\n                }\n            }\n            let (date, dateApply) = dateLayout(TextNodeLayoutArguments(attributedString: ayuDateText, backgroundColor: nil, maximumNumberOfLines: 1, truncationType: .middle, constrainedSize: arguments.constrainedSize, alignment: .natural, cutout: nil, insets: UIEdgeInsets()))\n"""
    return base.replace_once(text, old, new, "deleted-marker-only-color")


def patch_deleted_alpha(text: str) -> str:
    old_create = """            let node = (viewClassName as! ChatMessageItemView.Type).init(rotated: self.controllerInteraction.chatIsRotated)\n            node.setupItem(self, synchronousLoad: synchronousLoads)\n            \n            let nodeLayout = node.asyncLayout()\n"""
    new_create = """            let node = (viewClassName as! ChatMessageItemView.Type).init(rotated: self.controllerInteraction.chatIsRotated)\n            node.setupItem(self, synchronousLoad: synchronousLoads)\n            // AYU_IOS_PATCH_v0_3: one O(1) Atomic lookup per configured item.\n            // No timers, polling or per-frame work.\n            let ayuIsDeleted = AyuRuntimeSettings.isDeleted(self.message.id)\n            if ayuIsDeleted {\n                AyuRuntimeSettings.registerDeletedMessageId(self.message.id)\n            }\n            node.alpha = ayuIsDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n            \n            let nodeLayout = node.asyncLayout()\n"""
    text = base.replace_once(text, old_create, new_create, "deleted-alpha-create")

    old_update = """            if let nodeValue = node() as? ChatMessageItemView {\n                nodeValue.setupItem(self, synchronousLoad: false)\n                \n                let nodeLayout = nodeValue.asyncLayout()\n"""
    new_update = """            if let nodeValue = node() as? ChatMessageItemView {\n                nodeValue.setupItem(self, synchronousLoad: false)\n                let ayuIsDeleted = AyuRuntimeSettings.isDeleted(self.message.id)\n                if ayuIsDeleted {\n                    AyuRuntimeSettings.registerDeletedMessageId(self.message.id)\n                }\n                nodeValue.alpha = ayuIsDeleted ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : 1.0\n                \n                let nodeLayout = nodeValue.asyncLayout()\n"""
    return base.replace_once(text, old_update, new_update, "deleted-alpha-update")


def patch_message_context_read(text: str) -> str:
    anchor = """        return ContextController.Items(content: .list(actions), tip: nil)\n"""
    addition = """        // AYU_IOS_PATCH_v0_3: explicit one-message/chat read escape hatch.\n        // It is deliberately appended after every stock action, so it is the\n        // final context-menu item exactly when Ghost + no-read are active.\n        if AyuRuntimeSettings.suppressReadMessages, let ayuMessage = messages.first, ayuMessage.effectivelyIncoming(context.account.peerId) {\n            if !actions.isEmpty {\n                actions.append(.separator)\n            }\n            actions.append(.action(ContextMenuActionItem(text: \"Прочитать\", icon: { theme in\n                return generateTintedImage(image: UIImage(bundleImageName: \"Chat/Context Menu/MarkAsRead\"), color: theme.actionSheet.primaryTextColor)\n            }, action: { _, f in\n                AyuRuntimeSettings.allowNextRead(peerId: ayuMessage.id.peerId)\n                let _ = context.engine.messages.applyMaxReadIndexInteractively(index: ayuMessage.index).startStandalone()\n                f(.dismissWithoutContent)\n            })))\n        }\n\n"""
    return base.replace_once(text, anchor, addition + anchor, "message-context-manual-read")


# Override the crashfix/base transforms before running the normal patcher.
base.patch_read_state = patch_read_state
base.patch_status_color = patch_status_marker_only


if __name__ == "__main__":
    base.main()

    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").expanduser().resolve()
    base.patch_file(
        root / "submodules/TelegramUI/Components/Chat/ChatMessageItemImpl/Sources/ChatMessageItemImpl.swift",
        patch_deleted_alpha,
    )
    base.patch_file(
        root / "submodules/TelegramUI/Sources/ChatInterfaceStateContextMenus.swift",
        patch_message_context_read,
    )
    print("[ayu-v03-ui-v2] DONE")
