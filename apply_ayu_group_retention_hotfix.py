#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_DELETED_CANONICAL_RETENTION_v0_3"
RANGE_MARK = "AYU_DELETED_RANGE_RETENTION_v0_3"
DARK_THEME_MARK = "AYU_DELETED_DARK_THEME_BACKDROP_v0_3"


def replace_case_sections(text: str, start_token: str, end_token: str, replacement: str, label: str, minimum: int = 1) -> str:
    positions: list[tuple[int, int]] = []
    search_from = 0
    while True:
        start = text.find(start_token, search_from)
        if start < 0:
            break
        end = text.find(end_token, start + len(start_token))
        if end < 0:
            raise RuntimeError(f"{label}: end anchor missing after occurrence {len(positions) + 1}")
        positions.append((start, end))
        search_from = end
    if len(positions) < minimum:
        raise RuntimeError(f"{label}: expected at least {minimum} canonical replay section(s), found {len(positions)}")
    for start, end in reversed(positions):
        text = text[:start] + replacement + text[end:]
    return text


def patch_canonical_deletes(text: str) -> str:
    if MARK in text:
        return text

    global_start = "            case let .DeleteMessagesWithGlobalIds(ids):\n"
    direct_start = "            case let .DeleteMessages(ids):\n"
    min_start = "            case let .UpdateMinAvailableMessage(id):\n"

    global_replacement = r'''            case let .DeleteMessagesWithGlobalIds(ids):
                // AYU_DELETED_CANONICAL_RETENTION_v0_3
                // Final safety net for startup differences / reconnect sync. If a
                // remote-deleted message is already known to Ayu, never let a later
                // canonical replay remove it from Postbox.
                let ayuEffectiveGlobalIds: [Int32]
                if AyuRuntimeSettings.keepDeletedMessages {
                    let ayuProtectedGlobalIds = Set(transaction.messageIdsForGlobalIds(ids).filter { AyuRuntimeSettings.isDeleted($0) }.map { $0.id })
                    ayuEffectiveGlobalIds = ids.filter { !ayuProtectedGlobalIds.contains($0) }
                } else {
                    ayuEffectiveGlobalIds = ids
                }
                if !ayuEffectiveGlobalIds.isEmpty {
                    var resourceIds: [MediaResourceId] = []
                    transaction.deleteMessagesWithGlobalIds(ayuEffectiveGlobalIds, forEachMedia: { media in
                        addMessageMediaResourceIdsToRemove(media: media, resourceIds: &resourceIds)
                    })
                    if !resourceIds.isEmpty {
                        let _ = mediaBox.removeCachedResources(Array(Set(resourceIds)), force: true).start()
                    }
                }
                // Keep Telegram's delete event semantics even when the local message
                // is retained, so Ayu's marker/UI refresh still fires normally.
                deletedMessageIds.append(contentsOf: ids.map { .global($0) })
'''
    text = replace_case_sections(text, global_start, direct_start, global_replacement, "global canonical delete retention", minimum=1)

    direct_replacement = r'''            case let .DeleteMessages(ids):
                // AYU_DELETED_CANONICAL_RETENTION_v0_3
                let ayuEffectiveIds: [MessageId]
                if AyuRuntimeSettings.keepDeletedMessages {
                    ayuEffectiveIds = ids.filter { !AyuRuntimeSettings.isDeleted($0) }
                } else {
                    ayuEffectiveIds = ids
                }
                if !ayuEffectiveIds.isEmpty {
                    _internal_deleteMessages(transaction: transaction, mediaBox: mediaBox, ids: ayuEffectiveIds, manualAddMessageThreadStatsDifference: { id, add, remove in
                        addMessageThreadStatsDifference(threadKey: id, remove: remove, addedMessagePeer: nil, addedMessageId: nil, isOutgoing: false)
                    })
                }
                deletedMessageIds.append(contentsOf: ids.map { .messageId($0) })
'''
    text = replace_case_sections(text, direct_start, min_start, direct_replacement, "direct canonical delete retention", minimum=1)

    # UpdateMinAvailableMessage is a second cleanup path used heavily by channels /
    # supergroups after reconnect. Preserve only Ayu-marked messages in the cleared
    # range, while letting Telegram prune every ordinary message exactly as before.
    search_from = 0
    patched = 0
    while True:
        start = text.find(min_start, search_from)
        if start < 0:
            break
        delete_anchor = "                var resourceIds: [MediaResourceId] = []\n                transaction.deleteMessagesInRange(peerId: id.peerId, namespace: id.namespace, minId: 1, maxId: id.id, forEachMedia: { media in\n"
        delete_pos = text.find(delete_anchor, start, start + 5000)
        if delete_pos < 0:
            raise RuntimeError(f"range retention: deleteMessagesInRange anchor missing at occurrence {patched + 1}")
        if RANGE_MARK in text[start:delete_pos]:
            search_from = delete_pos + len(delete_anchor)
            continue

        preserve = r'''                // AYU_DELETED_RANGE_RETENTION_v0_3
                // Channel/supergroup sync may advance availableMinId after an app
                // restart and delete an entire Postbox range. Snapshot only the
                // already-marked Ayu messages in that range, run Telegram's normal
                // prune, then put those few messages back. No polling / frame work.
                var ayuPreservedMessages: [StoreMessage] = []
                var ayuProtectedResourceIds = Set<MediaResourceId>()
                if AyuRuntimeSettings.keepDeletedMessages {
                    for ayuId in AyuRuntimeSettings.deletedMessageIds(peerId: id.peerId) {
                        guard ayuId.namespace == id.namespace, ayuId.id >= 1, ayuId.id <= id.id else {
                            continue
                        }
                        guard let ayuMessage = transaction.getMessage(ayuId) else {
                            continue
                        }
                        var ayuMessageResourceIds: [MediaResourceId] = []
                        for media in ayuMessage.media {
                            addMessageMediaResourceIdsToRemove(media: media, resourceIds: &ayuMessageResourceIds)
                        }
                        ayuProtectedResourceIds.formUnion(ayuMessageResourceIds)
                        ayuPreservedMessages.append(StoreMessage(
                            id: ayuMessage.id,
                            customStableId: nil,
                            globallyUniqueId: ayuMessage.globallyUniqueId,
                            groupingKey: ayuMessage.groupingKey,
                            threadId: ayuMessage.threadId,
                            timestamp: ayuMessage.timestamp,
                            flags: StoreMessageFlags(ayuMessage.flags),
                            tags: ayuMessage.tags,
                            globalTags: ayuMessage.globalTags,
                            localTags: ayuMessage.localTags,
                            forwardInfo: ayuMessage.forwardInfo.flatMap(StoreMessageForwardInfo.init),
                            authorId: ayuMessage.author?.id,
                            text: ayuMessage.text,
                            attributes: ayuMessage.attributes,
                            media: ayuMessage.media
                        ))
                    }
                }

'''
        text = text[:delete_pos] + preserve + text[delete_pos:]
        # Locate the resource cleanup after the just-shifted delete block and add
        # restore/filter immediately before it.
        cleanup_anchor = "                if !resourceIds.isEmpty {\n                    let _ = mediaBox.removeCachedResources(Array(Set(resourceIds)), force: true).start()\n                }\n"
        cleanup_pos = text.find(cleanup_anchor, delete_pos + len(preserve), delete_pos + len(preserve) + 5000)
        if cleanup_pos < 0:
            raise RuntimeError(f"range retention: resource cleanup anchor missing at occurrence {patched + 1}")
        restore = r'''                if !ayuPreservedMessages.isEmpty {
                    let _ = transaction.addMessages(ayuPreservedMessages, location: .Random)
                }
                if !ayuProtectedResourceIds.isEmpty {
                    resourceIds.removeAll(where: { ayuProtectedResourceIds.contains($0) })
                }
'''
        text = text[:cleanup_pos] + restore + text[cleanup_pos:]
        patched += 1
        search_from = cleanup_pos + len(restore) + len(cleanup_anchor)

    if patched < 1:
        raise RuntimeError(f"range retention: expected at least 1 replay path, patched {patched}")
    return text


def patch_dark_theme_deleted_bubble(root: Path) -> None:
    path = root / "submodules/TelegramUI/Components/Chat/ChatMessageBubbleItemNode/Sources/ChatMessageBubbleItemNode.swift"
    text = path.read_text(encoding="utf-8")
    if DARK_THEME_MARK in text:
        return

    old_alpha = '''        // AYU_DELETED_BAKED_ALPHA_v0_3: use one cached stock bubble image with\n        // alpha baked into its pixels. This avoids the dark-theme color shift caused\n        // by compositing both the normal and wallpaper bubble nodes at half alpha.\n        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? CGFloat(AyuRuntimeSettings.deletedMessageAlpha) : nil\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n        strongSelf.backgroundNode.alpha = 1.0\n        strongSelf.backgroundWallpaperNode.alpha = ayuDeletedVisible ? 0.0 : 1.0\n'''
    new_alpha = '''        // AYU_DELETED_BAKED_ALPHA_v0_3: keep Telegram's native bubble source.\n        // Some dark themes render the bubble through WallpaperBubbleBackgroundNode\n        // instead of a UIImage. Prepare the image alpha here, then after setType\n        // choose exactly the source Telegram actually produced.\n        let ayuDeletedAlpha = CGFloat(AyuRuntimeSettings.deletedMessageAlpha)\n        let ayuTelegramThemeDeleted = ayuDeletedVisible && ayuDeletedBackgroundColor == nil\n        strongSelf.backgroundNode.ayuCustomFillColor = ayuDeletedBackgroundColor\n        strongSelf.backgroundNode.ayuCustomImageAlpha = ayuDeletedVisible ? ayuDeletedAlpha : nil\n        let ayuBackgroundMaskMode = ayuDeletedBackgroundColor == nil ? strongSelf.backgroundMaskMode : false\n        strongSelf.backgroundNode.alpha = 1.0\n        strongSelf.backgroundWallpaperNode.alpha = 1.0\n'''
    if text.count(old_alpha) != 1:
        raise RuntimeError(f"dark-theme deleted alpha block: expected 1 anchor, found {text.count(old_alpha)}")
    text = text.replace(old_alpha, new_alpha, 1)

    set_type_anchor = '''        strongSelf.backgroundNode.setType(type: backgroundType, highlighted: false, graphics: graphics, maskMode: ayuBackgroundMaskMode, hasWallpaper: hasWallpaper, transition: legacyTransition, backgroundNode: presentationContext.backgroundNode)\n        strongSelf.backgroundWallpaperNode.setType(type: backgroundType, theme: item.presentationData.theme, essentialGraphics: graphics, maskMode: strongSelf.backgroundMaskMode, backgroundNode: presentationContext.backgroundNode)\n'''
    post_set_type = set_type_anchor + '''\n        // AYU_DELETED_DARK_THEME_BACKDROP_v0_3\n        // If Telegram produced a normal bubble image, its alpha is already baked and\n        // cached by ChatMessageBackground. If the image is nil, the theme is using\n        // the wallpaper/backdrop bubble path; fade that one layer instead. Never hide\n        // both layers, and never change text/media/status opacity.\n        if ayuTelegramThemeDeleted && !strongSelf.backgroundNode.hasImage {\n            strongSelf.backgroundWallpaperNode.alpha = ayuDeletedAlpha\n        } else if ayuDeletedVisible && ayuDeletedBackgroundColor != nil {\n            strongSelf.backgroundWallpaperNode.alpha = 0.0\n        } else {\n            strongSelf.backgroundWallpaperNode.alpha = 1.0\n        }\n'''
    if text.count(set_type_anchor) != 1:
        raise RuntimeError(f"dark-theme post-setType anchor: expected 1, found {text.count(set_type_anchor)}")
    text = text.replace(set_type_anchor, post_set_type, 1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_group_retention_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManagementUtils.swift"
    if not path.exists():
        raise RuntimeError(f"missing Telegram source: {path}")

    text = path.read_text(encoding="utf-8")
    text = patch_canonical_deletes(text)
    path.write_text(text, encoding="utf-8")
    patch_dark_theme_deleted_bubble(root)
    print("[ayu-group-retention] canonical delete + channel min-range retention + dark-theme Telegram bubble installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
