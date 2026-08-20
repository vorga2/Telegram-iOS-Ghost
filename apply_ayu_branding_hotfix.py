#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

MARK = "AYU_APP_DISPLAY_NAME_v0_3"
CALLKIT_MARK = "AYU_CALLKIT_DISPLAY_NAME_v0_3"
PILL_MARK = "AYU_CALL_STATUS_PILL_v0_3"


def one(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_ayu_branding_hotfix.py <Telegram-iOS root>", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    # App display name used by the built IPA / SpringBoard metadata.
    build_path = root / "Telegram/BUILD"
    build = build_path.read_text(encoding="utf-8")
    if MARK not in build:
        old = '''plist_fragment(
    name = "AppNameInfoPlist",
    extension = "plist",
    template =
    """
    <key>CFBundleDisplayName</key>
    <string>Telegram</string>
'''
        new = f'''# {MARK}
plist_fragment(
    name = "AppNameInfoPlist",
    extension = "plist",
    template =
    """
    <key>CFBundleDisplayName</key>
    <string>AyuGram</string>
'''
        build = one(build, old, new, "Bazel app display name")
        build_path.write_text(build, encoding="utf-8")

    # Keep fallback/project-style plists consistent.
    for relative in ("Telegram/Telegram-iOS/InfoBazel.plist", "Telegram/Telegram-iOS/Info.plist"):
        path = root / relative
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        anchor = "\t<key>CFBundleDisplayName</key>\n\t<string>${APP_NAME}</string>"
        if anchor in text:
            text = text.replace(anchor, "\t<key>CFBundleDisplayName</key>\n\t<string>AyuGram</string>", 1)
            path.write_text(text, encoding="utf-8")

    # A localized InfoPlist.strings can override CFBundleDisplayName.
    for path in (root / "Telegram/Telegram-iOS").glob("*.lproj/InfoPlist.strings"):
        text = path.read_text(encoding="utf-8")
        updated, count = re.subn(
            r'^\s*"CFBundleDisplayName"\s*=\s*"[^"]*"\s*;\s*$',
            '"CFBundleDisplayName" = "AyuGram";',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if count:
            path.write_text(updated, encoding="utf-8")

    # Keep CallKit's provider branding consistent too.
    callkit_path = root / "submodules/TelegramCallsUI/Sources/CallKitIntegration.swift"
    if not callkit_path.exists():
        raise RuntimeError(f"missing CallKit source: {callkit_path}")
    callkit = callkit_path.read_text(encoding="utf-8")
    if CALLKIT_MARK not in callkit:
        old = '        let providerConfiguration = CXProviderConfiguration(localizedName: "Telegram")\n'
        new = (
            f'        // {CALLKIT_MARK}\n'
            '        let providerConfiguration = CXProviderConfiguration(localizedName: "AyuGram")\n'
        )
        callkit = one(callkit, old, new, "CallKit provider display name")
        callkit_path.write_text(callkit, encoding="utf-8")

    # iOS owns the real colored call/status pill. For screenshots inside AyuGram,
    # draw a tiny non-interactive overlay window above the app/status-bar area.
    # It is 100% event-driven: no timer, no display link, no per-frame work.
    app_delegate_path = root / "submodules/TelegramUI/Sources/AppDelegate.swift"
    if not app_delegate_path.exists():
        raise RuntimeError(f"missing AppDelegate source: {app_delegate_path}")
    app_delegate = app_delegate_path.read_text(encoding="utf-8")

    if PILL_MARK not in app_delegate:
        class_anchor = '''private enum QueuedWakeup: Int32 {
    case call
    case backgroundLocation
}

final class SharedApplicationContext {
'''
        class_insert = f'''private enum QueuedWakeup: Int32 {{
    case call
    case backgroundLocation
}}

// {PILL_MARK}
private final class AyuCallStatusPillWindow: UIWindow {{
    override func hitTest(_ point: CGPoint, with event: UIEvent?) -> UIView? {{
        return nil
    }}
}}

private final class AyuCallStatusPillOverlay {{
    private var window: AyuCallStatusPillWindow?

    func setActive(_ active: Bool, scene: UIWindowScene?) {{
        if !active {{
            self.window?.isHidden = true
            self.window = nil
            return
        }}

        guard let scene = scene else {{
            return
        }}
        if let window = self.window {{
            window.isHidden = false
            return
        }}

        let overlayWindow = AyuCallStatusPillWindow(windowScene: scene)
        overlayWindow.frame = scene.coordinateSpace.bounds
        overlayWindow.windowLevel = UIWindow.Level(rawValue: UIWindow.Level.alert.rawValue + 1000.0)
        overlayWindow.backgroundColor = .clear
        overlayWindow.isUserInteractionEnabled = false

        let controller = UIViewController()
        controller.view.backgroundColor = .clear
        controller.view.isUserInteractionEnabled = false
        overlayWindow.rootViewController = controller

        let pill = UIView()
        // Deep purple from the requested AyuGram reference swatch (#342B4E).
        pill.backgroundColor = UIColor(red: 52.0 / 255.0, green: 43.0 / 255.0, blue: 78.0 / 255.0, alpha: 1.0)
        pill.layer.cornerRadius = 12.0
        if #available(iOS 13.0, *) {{
            pill.layer.cornerCurve = .continuous
        }}
        pill.translatesAutoresizingMaskIntoConstraints = false
        controller.view.addSubview(pill)

        let icon = UIImageView(image: UIImage(systemName: "paperplane.fill"))
        icon.tintColor = .white
        icon.contentMode = .scaleAspectFit
        icon.translatesAutoresizingMaskIntoConstraints = false

        let label = UILabel()
        label.text = "AYUGRAM"
        label.textColor = .white
        label.font = UIFont.systemFont(ofSize: 10.5, weight: .semibold)
        label.adjustsFontSizeToFitWidth = false
        label.translatesAutoresizingMaskIntoConstraints = false

        let content = UIStackView(arrangedSubviews: [icon, label])
        content.axis = .horizontal
        content.alignment = .center
        content.spacing = 4.0
        content.translatesAutoresizingMaskIntoConstraints = false
        pill.addSubview(content)

        NSLayoutConstraint.activate([
            pill.leadingAnchor.constraint(equalTo: controller.view.leadingAnchor, constant: 14.0),
            pill.topAnchor.constraint(equalTo: controller.view.topAnchor, constant: 7.0),
            pill.widthAnchor.constraint(equalToConstant: 112.0),
            pill.heightAnchor.constraint(equalToConstant: 24.0),

            icon.widthAnchor.constraint(equalToConstant: 11.0),
            icon.heightAnchor.constraint(equalToConstant: 11.0),
            content.centerXAnchor.constraint(equalTo: pill.centerXAnchor),
            content.centerYAnchor.constraint(equalTo: pill.centerYAnchor)
        ])

        overlayWindow.isHidden = false
        self.window = overlayWindow
    }}
}}

final class SharedApplicationContext {{
'''
        app_delegate = one(app_delegate, class_anchor, class_insert, "Ayu call pill class anchor")

        property_anchor = '''    private var memoryUsageOverlayView: UILabel?\n    \n    private var buildConfig: BuildConfig?\n'''
        property_insert = '''    private var memoryUsageOverlayView: UILabel?\n    private var ayuCallStatusPillOverlay: AyuCallStatusPillOverlay?\n    \n    private var buildConfig: BuildConfig?\n'''
        app_delegate = one(app_delegate, property_anchor, property_insert, "Ayu call pill property anchor")

        signal_anchor = '''        var hasActiveCalls: Signal<Bool, NoError> = .single(false)\n        if CallKitIntegration.isAvailable, let callKitIntegration = CallKitIntegration.shared {\n            hasActiveCalls = callKitIntegration.hasActiveCalls\n        }\n        self.hasActiveAudioSession.set(\n'''
        signal_insert = '''        var hasActiveCalls: Signal<Bool, NoError> = .single(false)\n        if CallKitIntegration.isAvailable, let callKitIntegration = CallKitIntegration.shared {\n            hasActiveCalls = callKitIntegration.hasActiveCalls\n        }\n        self.watchedCallsDisposables.add((hasActiveCalls\n        |> distinctUntilChanged\n        |> deliverOnMainQueue).start(next: { [weak self] active in\n            guard let self else {\n                return\n            }\n            if active {\n                let overlay: AyuCallStatusPillOverlay\n                if let current = self.ayuCallStatusPillOverlay {\n                    overlay = current\n                } else {\n                    overlay = AyuCallStatusPillOverlay()\n                    self.ayuCallStatusPillOverlay = overlay\n                }\n                overlay.setActive(true, scene: self.window?.windowScene)\n            } else {\n                self.ayuCallStatusPillOverlay?.setActive(false, scene: self.window?.windowScene)\n                self.ayuCallStatusPillOverlay = nil\n            }\n        }))\n        self.hasActiveAudioSession.set(\n'''
        app_delegate = one(app_delegate, signal_anchor, signal_insert, "Ayu call pill signal anchor")
        app_delegate_path.write_text(app_delegate, encoding="utf-8")

    if "<string>AyuGram</string>" not in build_path.read_text(encoding="utf-8"):
        raise RuntimeError("AyuGram Bazel display name was not installed")
    callkit_verify = callkit_path.read_text(encoding="utf-8")
    if 'CXProviderConfiguration(localizedName: "AyuGram")' not in callkit_verify:
        raise RuntimeError("AyuGram CallKit display name was not installed")
    app_delegate_verify = app_delegate_path.read_text(encoding="utf-8")
    if PILL_MARK not in app_delegate_verify or 'label.text = "AYUGRAM"' not in app_delegate_verify:
        raise RuntimeError("AyuGram call status pill was not installed")
    if "Timer" in app_delegate_verify[app_delegate_verify.index(PILL_MARK):app_delegate_verify.index("final class SharedApplicationContext")]:
        raise RuntimeError("AyuGram call status pill must remain timer-free")

    print("[ayu-branding] AyuGram display name + CallKit name + event-driven purple call pill")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
