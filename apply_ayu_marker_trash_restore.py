#!/usr/bin/env python3
from pathlib import Path
import sys

MARK = "AYU_MARKER_TRASH_RESTORE_v0_3"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_marker_trash_restore.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    runtime = root / "submodules/TelegramCore/Sources/State/AyuRuntimeSettings.swift"
    text = runtime.read_text(encoding="utf-8")

    if MARK not in text:
        # Reuse the existing .compact persisted enum value so old settings remain
        # compatible; only its visible glyph changes back to a trash can.
        old_prefix = '''        case .compact:\n            return "◉"\n'''
        if old_prefix in text:
            text = text.replace(
                old_prefix,
                '''        case .compact:\n            // AYU_MARKER_TRASH_RESTORE_v0_3\n            return "🗑"\n''',
                1,
            )
        elif '''        case .compact:\n            return "🗑"\n''' not in text:
            raise RuntimeError("trash marker restore: compact marker prefix anchor missing")

        old_title = '''        case .compact:\n            return "Глазик"\n'''
        if old_title in text:
            text = text.replace(
                old_title,
                '''        case .compact:\n            return "🗑"\n''',
                1,
            )

    runtime.write_text(text, encoding="utf-8")

    settings = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/AyuSettingsController.swift"
    text = settings.read_text(encoding="utf-8")

    old_options = '        let options: [(AyuDeletedMarkerStyle, String)] = [(.text, " "), (.trash, "👀"), (.cross, "❌")]\n'
    new_options = '        let options: [(AyuDeletedMarkerStyle, String)] = [(.text, " "), (.trash, "👀"), (.cross, "❌"), (.compact, "🗑")]\n'

    if old_options in text:
        text = text.replace(old_options, new_options, 1)
    elif new_options not in text:
        raise RuntimeError("trash marker restore: icon-only picker anchor missing")

    settings.write_text(text, encoding="utf-8")

    print("[ayu-marker-trash] marker options: blank / 👀 / ❌ / 🗑")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
