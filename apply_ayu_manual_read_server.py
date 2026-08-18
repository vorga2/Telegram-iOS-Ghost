#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_MANUAL_READ_SERVER_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_manual_read_server.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramCore/Sources/PendingMessages/EnqueueMessage.swift"
    text = path.read_text(encoding="utf-8")

    if MARK in text:
        print(f"[ayu-manual-read-server] already patched: {path}")
        return 0

    old = '''// AYU_BEHAVIOR_HOTFIX_v0_3
public func ayuReadMessageThroughGhost(account: Account, index: MessageIndex) {
    guard AyuRuntimeSettings.snapshot.master else { return }
    AyuRuntimeSettings.allowNextRead(peerId: index.id.peerId)
    let _ = account.postbox.transaction { transaction -> Void in
        _internal_applyMaxReadIndexInteractively(transaction: transaction, stateManager: account.stateManager, index: index)
    }.start()
}

'''

    new = '''// AYU_BEHAVIOR_HOTFIX_v0_3
// AYU_MANUAL_READ_SERVER_v0_3
private enum AyuManualReadTarget {
    case cloud(Api.InputPeer)
    case secret(Api.InputEncryptedChat)
}

public func ayuReadMessageThroughGhost(account: Account, index: MessageIndex) {
    guard AyuRuntimeSettings.snapshot.master else { return }

    // Do not leave a one-shot Ghost allowance behind. The local Postbox read
    // state is applied first, while its normal background sync remains subject
    // to Ghost suppression. This explicit action performs exactly one direct
    // Telegram read request for the selected max id below.
    AyuRuntimeSettings.consumeManualReadAllowance(peerId: index.id.peerId)

    let signal = account.postbox.transaction { transaction -> AyuManualReadTarget? in
        // Telegram's own helper marks the selected incoming message and every
        // older message up to the same MessageIndex as read locally.
        _internal_applyMaxReadIndexInteractively(
            transaction: transaction,
            stateManager: account.stateManager,
            index: index
        )

        guard let peer = transaction.getPeer(index.id.peerId) else {
            return nil
        }
        if index.id.peerId.namespace == Namespaces.Peer.SecretChat {
            if let input = apiInputSecretChat(peer) {
                return .secret(input)
            }
        } else if let input = apiInputPeer(peer) {
            return .cloud(input)
        }
        return nil
    }
    |> mapToSignal { target -> Signal<Void, NoError> in
        guard let target else {
            return .complete()
        }

        switch target {
        case let .secret(input):
            return account.network.request(
                Api.functions.messages.readEncryptedHistory(peer: input, maxDate: index.timestamp)
            )
            |> `catch` { _ -> Signal<Api.Bool, NoError> in
                return .complete()
            }
            |> mapToSignal { _ -> Signal<Void, NoError> in
                return .complete()
            }

        case let .cloud(input):
            switch input {
            case let .inputPeerChannel(data):
                return account.network.request(
                    Api.functions.channels.readHistory(
                        channel: Api.InputChannel.inputChannel(.init(channelId: data.channelId, accessHash: data.accessHash)),
                        maxId: index.id.id
                    )
                )
                |> `catch` { _ -> Signal<Api.Bool, NoError> in
                    return .complete()
                }
                |> mapToSignal { _ -> Signal<Void, NoError> in
                    return .complete()
                }

            default:
                return account.network.request(
                    Api.functions.messages.readHistory(peer: input, maxId: index.id.id)
                )
                |> map(Optional.init)
                |> `catch` { _ -> Signal<Api.messages.AffectedMessages?, NoError> in
                    return .single(nil)
                }
                |> mapToSignal { result -> Signal<Void, NoError> in
                    if let result {
                        switch result {
                        case let .affectedMessages(data):
                            account.stateManager.addUpdateGroups([.updatePts(pts: data.pts, ptsCount: data.ptsCount)])
                        }
                    }
                    return .complete()
                }
            }
        }
    }

    let _ = signal.startStandalone()
}

'''

    text = one(text, old, new, "manual Read helper")
    path.write_text(text, encoding="utf-8")
    print("[ayu-manual-read-server] explicit selected-max server read installed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
