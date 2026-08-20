#!/usr/bin/env python3
from __future__ import annotations

import os
import py_compile
import subprocess
import sys
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    workspace = Path(os.environ.get("GITHUB_WORKSPACE", Path(__file__).resolve().parent)).resolve()
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    telegram = runner_temp / "Telegram-iOS"
    require(telegram.exists(), "branding verifier requires Telegram-iOS checkout")

    patcher = workspace / "apply_ayu_branding_hotfix.py"
    py_compile.compile(str(patcher), doraise=True)
    subprocess.run([sys.executable, str(patcher), str(telegram)], check=True)

    build = (telegram / "Telegram/BUILD").read_text(encoding="utf-8")
    require("AYU_APP_DISPLAY_NAME_v0_3" in build, "AyuGram display-name marker missing")
    require("<string>AyuGram</string>" in build, "built IPA display name is not AyuGram")

    callkit = (telegram / "submodules/TelegramCallsUI/Sources/CallKitIntegration.swift").read_text(encoding="utf-8")
    require("AYU_CALLKIT_DISPLAY_NAME_v0_3" in callkit, "CallKit branding marker missing")
    require('CXProviderConfiguration(localizedName: "AyuGram")' in callkit, "CallKit provider is not branded AyuGram")

    app_delegate = (telegram / "submodules/TelegramUI/Sources/AppDelegate.swift").read_text(encoding="utf-8")
    require("AYU_CALL_STATUS_PILL_v0_3" in app_delegate, "AyuGram artificial call pill missing")
    require('label.text = "AYUGRAM"' in app_delegate, "AyuGram pill label missing")
    require("UIColor(red: 52.0 / 255.0, green: 43.0 / 255.0, blue: 78.0 / 255.0, alpha: 1.0)" in app_delegate, "requested purple pill color missing")
    require("UIWindow.Level(rawValue: UIWindow.Level.alert.rawValue + 1000.0)" in app_delegate, "call pill is not placed in the high overlay window")
    require("watchedCallsDisposables.add((hasActiveCalls" in app_delegate, "call pill is not driven by the existing active-call signal")
    require("|> distinctUntilChanged" in app_delegate, "call pill signal is not de-duplicated")

    start = app_delegate.index("AYU_CALL_STATUS_PILL_v0_3")
    end = app_delegate.index("final class SharedApplicationContext", start)
    overlay = app_delegate[start:end]
    for forbidden in ("Timer", "CADisplayLink", "DispatchSourceTimer", "setNeedsDisplay"):
        require(forbidden not in overlay, f"call pill must stay zero-polling: found {forbidden}")

    print("=== AYUGRAM BRANDING VERIFY SUCCESS ===", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"=== AYUGRAM BRANDING VERIFY FAILURE ===\n{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise
