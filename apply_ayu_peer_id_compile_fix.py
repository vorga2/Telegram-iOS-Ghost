#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MARK = "AYU_PEER_ID_INFO_v1"
FIX_MARK = "AYU_PEER_ID_INFO_SCOPE_FIX_v2"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_peer_id_compile_fix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    path = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/PeerInfoProfileItems.swift"
    text = path.read_text(encoding="utf-8")

    if FIX_MARK in text:
        print(f"[ayu-peer-id-fix] already patched: {path}")
        return 0

    marker = "    // AYU_PEER_ID_INFO_v1: technical info block at the bottom of the profile.\n"
    marker_count = text.count(marker)
    if marker_count != 1:
        raise RuntimeError(f"peer id block: expected exactly 1 old marker, found {marker_count}")

    # The original essentials patch anchored on the end of editingItems(), not
    # infoItems(). In that scope data.peer is EnginePeer? and the InfoSection
    # variable currentPeerInfoSection does not exist. Remove that misplaced block.
    old_start = text.index(marker)
    old_end = text.index("    var result: [(AnyHashable, [PeerInfoScreenItem])] = []\n", old_start)
    text = text[:old_start] + text[old_end:]

    # This anchor is unique to infoItems(): its result is enumerated using
    # InfoSection. editingItems() uses a different Section enum.
    anchor = """    var result: [(AnyHashable, [PeerInfoScreenItem])] = []
    for section in InfoSection.allCases {
"""
    if text.count(anchor) != 1:
        raise RuntimeError(f"infoItems result anchor: expected 1, found {text.count(anchor)}")

    block = """    // AYU_PEER_ID_INFO_v1: technical info block at the bottom of the profile.
    // AYU_PEER_ID_INFO_SCOPE_FIX_v2: this must live inside infoItems(), where
    // data is unwrapped and items is keyed by InfoSection.
    if AyuRuntimeSettings.snapshot.peerIdStyle != 0 {
        let ayuPeerId = data.peer.id
        let ayuInternalId = ayuPeerId.id._internalGetInt64Value()
        let ayuIdText: String
        if AyuRuntimeSettings.snapshot.peerIdStyle == 2 {
            switch ayuPeerId.namespace {
            case Namespaces.Peer.CloudChannel:
                ayuIdText = "-100\\(ayuInternalId)"
            case Namespaces.Peer.CloudGroup:
                ayuIdText = "-\\(ayuInternalId)"
            default:
                ayuIdText = "\\(ayuInternalId)"
            }
        } else {
            ayuIdText = "\\(ayuInternalId)"
        }

        var ayuDcLine = ""
        if let ayuResource = data.peer.profileImageRepresentations.first?.resource as? CloudPeerPhotoSizeMediaResource {
            let dc = ayuResource.datacenterId
            let city: String
            switch dc {
            case 1, 3:
                city = "Miami, US"
            case 2, 4:
                city = "Amsterdam, NL"
            case 5:
                city = "Singapore, SG"
            default:
                city = ""
            }
            ayuDcLine = city.isEmpty ? "DC\\(dc)" : "DC\\(dc), \\(city)"
        }

        var ayuFooterText = "ID: \\(ayuIdText)"
        if !ayuDcLine.isEmpty {
            ayuFooterText += "\\n\\(ayuDcLine)"
        }
        items[.peerInfoTrailing]!.append(PeerInfoScreenCommentItem(id: 0xA0091101, text: ayuFooterText))
    }

"""

    text = text.replace(anchor, block + anchor, 1)
    path.write_text(text, encoding="utf-8")
    print(f"[ayu-peer-id-fix] moved peer ID/DC block into infoItems(): {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
