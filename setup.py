"""py2app ビルド定義(alias モード前提)。

`python setup.py py2app -A` で、この Mac の venv を参照する .app を生成する。
重要: バンドルの identity を com.local.z407remote にし、Info.plist に
NSBluetoothAlwaysUsageDescription を持たせることで、
  - メニューバー常駐(LSUIElement: Dock 非表示)
  - CoreBluetooth 使用時に macOS がアプリを強制終了しない
を成立させる。`exec python` 方式だと identity が org.python.python になり
これらが効かない(アイコンが出ない/Bluetooth でクラッシュ)ため py2app を使う。
"""

from setuptools import setup

APP = ["z407_app.py"]
OPTIONS = {
    "iconfile": "assets/Z407Remote.icns",
    "plist": {
        "CFBundleName": "Z407 Remote",
        "CFBundleDisplayName": "Z407 Remote",
        "CFBundleIdentifier": "com.local.z407remote",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
        "LSUIElement": True,
        "NSBluetoothAlwaysUsageDescription":
            "Z407 Remote uses Bluetooth to control your Logitech Z407 speakers.",
        "NSBluetoothPeripheralUsageDescription":
            "Z407 Remote uses Bluetooth to control your Logitech Z407 speakers.",
        "NSAppleEventsUsageDescription":
            "Z407 Remote controls Spotify (play/pause, track, now playing) via Apple Events.",
    },
    "packages": ["bleak"],
    "includes": ["WebKit", "Cocoa", "CoreBluetooth", "Foundation", "objc",
                 "panel", "z407_remote"],
}

setup(
    name="Z407 Remote",
    app=APP,
    options={"py2app": OPTIONS},
)
