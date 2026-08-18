#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_account_state_manager(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    old = """        func addUpdates(_ updates: Api.Updates) {\n            self.queue.async {\n                self.updateService?.addUpdates(updates)\n            }\n        }\n"""

    new = r'''        // AYU_IOS_DELETED_REALTIME_v0_3: keep the normal Postbox-driven UI
        // update path even though remote deletes themselves are suppressed. This is
        // event-driven: work happens only when Telegram receives a delete update.
        private func ayuRefreshPreservedDeletedMessages(_ updates: Api.Updates) {
            guard AyuRuntimeSettings.keepDeletedMessages else {
                return
            }

            var globalIds: [Int32] = []
            var messageIds: [MessageId] = []

            func collect(_ update: Api.Update) {
                switch update {
                case let .updateDeleteMessages(data):
                    globalIds.append(contentsOf: data.messages)
                case let .updateDeleteChannelMessages(data):
                    let peerId = PeerId(namespace: Namespaces.Peer.CloudChannel, id: PeerId.Id._internalFromInt64Value(data.channelId))
                    messageIds.append(contentsOf: data.messages.map {
                        MessageId(peerId: peerId, namespace: Namespaces.Message.Cloud, id: $0)
                    })
                default:
                    break
                }
            }

            switch updates {
            case let .updates(data):
                for update in data.updates {
                    collect(update)
                }
            case let .updatesCombined(data):
                for update in data.updates {
                    collect(update)
                }
            case let .updateShort(data):
                collect(data.update)
            case .updateShortChatMessage, .updateShortMessage, .updateShortSentMessage, .updatesTooLong:
                break
            }

            guard !globalIds.isEmpty || !messageIds.isEmpty else {
                return
            }

            // Mark first, before touching Postbox, so the normal chat relayout sees
            // the deleted state on its very first refresh.
            AyuRuntimeSettings.markDeletedGlobalIds(globalIds)
            AyuRuntimeSettings.markDeletedMessageIds(messageIds)

            let directMessageIds = messageIds
            let _ = (self.postbox.transaction { transaction -> [DeletedMessageId] in
                var resolvedMessageIds = directMessageIds
                if !globalIds.isEmpty {
                    let resolvedGlobalIds = transaction.messageIdsForGlobalIds(globalIds)
                    if !resolvedGlobalIds.isEmpty {
                        resolvedMessageIds.append(contentsOf: resolvedGlobalIds)
                        AyuRuntimeSettings.markDeletedMessageIds(resolvedGlobalIds)
                    }
                }

                // Re-store the exact same message. Postbox emits its ordinary message
                // update operation, which refreshes an already-visible chat item. No
                // polling, timers, full-history scan or per-frame work is introduced.
                var touched = Set<MessageId>()
                for id in resolvedMessageIds {
                    guard touched.insert(id).inserted else {
                        continue
                    }
                    transaction.updateMessage(id, update: { currentMessage in
                        return .update(StoreMessage(
                            id: currentMessage.id,
                            customStableId: nil,
                            globallyUniqueId: currentMessage.globallyUniqueId,
                            groupingKey: currentMessage.groupingKey,
                            threadId: currentMessage.threadId,
                            timestamp: currentMessage.timestamp,
                            flags: StoreMessageFlags(currentMessage.flags),
                            tags: currentMessage.tags,
                            globalTags: currentMessage.globalTags,
                            localTags: currentMessage.localTags,
                            forwardInfo: currentMessage.forwardInfo.flatMap(StoreMessageForwardInfo.init),
                            authorId: currentMessage.author?.id,
                            text: currentMessage.text,
                            attributes: currentMessage.attributes,
                            media: currentMessage.media
                        ))
                    })
                }

                var deletedEvents = globalIds.map { DeletedMessageId.global($0) }
                deletedEvents.append(contentsOf: directMessageIds.map { DeletedMessageId.messageId($0) })
                return deletedEvents
            }
            |> deliverOn(self.queue)).start(next: { [weak self] deletedEvents in
                guard let self, !deletedEvents.isEmpty else {
                    return
                }
                // Preserve Telegram's existing deletedMessages signal semantics for
                // any UI/controllers that already listen to AccountStateManager.
                self.deletedMessagesPipe.putNext(deletedEvents)
            })
        }

        func addUpdates(_ updates: Api.Updates) {
            self.queue.async {
                self.ayuRefreshPreservedDeletedMessages(updates)
                self.updateService?.addUpdates(updates)
            }
        }
'''

    text = replace_once(text, old, new, "AccountStateManager.addUpdates")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_deleted_realtime.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/State/AccountStateManager.swift"
    if not path.exists():
        raise RuntimeError(f"missing Telegram source: {path}")

    patch_account_state_manager(path)
    print("[ayu-deleted-realtime] event-driven visible-chat refresh installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
