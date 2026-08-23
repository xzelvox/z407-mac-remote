"""Logitech Z407 Remote — macOS メニューバー常駐アプリ(Aurora パネル / WKWebView)。

メニューバーの 🔊 を押すと NSPopover にデザイン(panel.HTML)を WKWebView で表示する。
- JS→Python: window.webkit.messageHandlers.bridge.postMessage({action,value})
- Python→JS: webview.evaluateJavaScript("applyState(<json>)")(メインスレッドのみ)
- 背景スレッドで asyncio ループを回し、bleak(BLE)/ osascript(Spotify・システム音量)を実行。

マッピング:
- 音量スライダー → macOS 出力音量(絶対値)
- 再生中・進捗・⏮⏯⏭ → Spotify(osascript)
- 入力 BT/AUX/USB・Bluetooth Pairing・Connect/状態 → Z407 BLE
"""

import asyncio
import json
import os
import threading
import weakref

import objc
from Foundation import NSObject, NSNull, NSMakeRect
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSViewController,
    NSPopover,
    NSPopoverBehaviorTransient,
    NSMinYEdge,
    NSAppearance,
    NSAppearanceNameDarkAqua,
    NSViewWidthSizable,
    NSViewHeightSizable,
)
from WebKit import WKWebView, WKWebViewConfiguration, WKUserContentController
from PyObjCTools import AppHelper

from z407_remote import Z407Remote
from panel import HTML

# --- 設定(言語永続化) ---
_SETTINGS_FILE = os.path.join(
    os.path.expanduser("~/Library/Application Support/Z407 Remote"), "settings.json"
)

# アプリ層からの動的メッセージの翻訳辞書
_MSG = {
    "ja": {
        "notConnected": "未接続です。先に Connect してください",
        "cancelReconnect": "再接続を中止しました",
        "btDenied": "Bluetooth 不許可: システム設定→プライバシーとセキュリティ→Bluetooth で許可",
        "searching": "Z407 を検索中…(試行 {attempt})",
        "searchHint": " (見つからない場合: Z407 の電源を入れ直す / リモコンのペアリングボタン)",
        "btApprove": "Bluetooth の許可を承認してください(未許可のため再試行中)",
        "connecting": "接続中…",
        "btNeedPerm": "Bluetooth の許可が必要(システム設定→Bluetooth)",
        "connectFail": "接続失敗: {err}",
        "cancelled": "中止しました",
        "resettingFor": "初期化のため接続中…(試行 {attempt})",
        "resetSent": "初期化送信。Z407 が再起動 → 新機器を先にペアリング → CONNECT で再接続",
        "resetFail": "初期化失敗: {err}",
        "pairingFor": "ペアリングのため接続中…(試行 {attempt})",
        "pairSent": "ペアリングモード送信。30秒以内に新機器を接続(Mac は音声枠を取り合う点に注意)",
        "pairFail": "ペアリング失敗: {err}",
        "spotifyErr": "Spotify を操作できません(起動 & オートメーション許可)",
        "spotifyNotInstalled": "Spotify がインストールされていません",
        "errPrefix": "エラー: {err}",
    },
    "en": {
        "notConnected": "Not connected. Connect first.",
        "cancelReconnect": "Reconnect cancelled",
        "btDenied": "Bluetooth not allowed: System Settings→Privacy & Security→Bluetooth",
        "searching": "Searching for Z407… (attempt {attempt})",
        "searchHint": " (If not found: power-cycle the Z407 / press the remote's pairing button)",
        "btApprove": "Please approve Bluetooth permission (retrying since not yet allowed)",
        "connecting": "Connecting…",
        "btNeedPerm": "Bluetooth permission required (System Settings→Bluetooth)",
        "connectFail": "Connection failed: {err}",
        "cancelled": "Cancelled",
        "resettingFor": "Connecting to reset… (attempt {attempt})",
        "resetSent": "Reset sent. Z407 reboots → pair the new device first → CONNECT to reconnect",
        "resetFail": "Reset failed: {err}",
        "pairingFor": "Connecting to pair… (attempt {attempt})",
        "pairSent": "Pairing mode sent. Connect a new device within 30s (note the Mac may compete for the audio slot)",
        "pairFail": "Pairing failed: {err}",
        "spotifyErr": "Cannot control Spotify (launch it & grant Automation permission)",
        "spotifyNotInstalled": "Spotify is not installed",
        "errPrefix": "Error: {err}",
    },
}

# --- AppleScript(osascript で実行) ---
_SYS_VOL_GET = "output volume of (get volume settings)"

# 状態取得: "running|state|title|artist|position|duration" を ~|~ 区切りで返す
# 注意: `player state as text` は構文エラーになるため、列挙定数と直接比較する。
_SPOTIFY_STATE = '''
if application "Spotify" is running then
    tell application "Spotify"
        set ps to player state
        if ps is playing then
            set stt to "playing"
        else if ps is paused then
            set stt to "paused"
        else
            return "1~|~stopped~|~~|~~|~0~|~0"
        end if
        set t to name of current track
        set ar to artist of current track
        set p to player position
        set d to (duration of current track) / 1000
        return "1~|~" & stt & "~|~" & t & "~|~" & ar & "~|~" & (p as text) & "~|~" & (d as text)
    end tell
else
    return "0~|~~|~~|~~|~0~|~0"
end if
'''

_SP_PLAYPAUSE = 'if application "Spotify" is running then\n    tell application "Spotify" to playpause\n    return "ok"\nelse\n    return ""\nend if'
_SP_NEXT = 'if application "Spotify" is running then\n    tell application "Spotify" to next track\n    return "ok"\nelse\n    return ""\nend if'
_SP_PREV = 'if application "Spotify" is running then\n    tell application "Spotify" to previous track\n    return "ok"\nelse\n    return ""\nend if'


def _spotify_installed() -> bool:
    """Spotify.app がインストールされているか(起動はしない)。"""
    try:
        from AppKit import NSWorkspace

        url = NSWorkspace.sharedWorkspace().URLForApplicationWithBundleIdentifier_(
            "com.spotify.client"
        )
        return url is not None
    except Exception:  # noqa: BLE001
        return False


def _bluetooth_status() -> str:
    """このアプリの Bluetooth 利用許可の状態を返す(notdetermined/restricted/denied/allowed)。"""
    try:
        from CoreBluetooth import CBCentralManager

        s = int(CBCentralManager.authorization())
        return {0: "notdetermined", 1: "restricted", 2: "denied", 3: "allowed"}.get(
            s, "unknown"
        )
    except Exception:  # noqa: BLE001
        return "unknown"


# === Cocoa デリゲート/ターゲット(app は weakref で参照しサイクルを避ける) ===
class _Target(NSObject):
    def initWithApp_(self, app):
        self = objc.super(_Target, self).init()
        if self is None:
            return None
        self._app = weakref.ref(app)
        return self

    def toggle_(self, sender):
        app = self._app()
        if app is not None:
            app.toggle_popover()


class _Bridge(NSObject):
    def initWithApp_(self, app):
        self = objc.super(_Bridge, self).init()
        if self is None:
            return None
        self._app = weakref.ref(app)
        return self

    def userContentController_didReceiveScriptMessage_(self, ucc, message):
        app = self._app()
        if app is None:
            return
        body = message.body()
        try:
            action = str(body["action"])
        except Exception:  # noqa: BLE001
            return
        value = body["value"] if "value" in body else None
        if value is None or isinstance(value, NSNull):
            value = None
        app.on_action(action, value)


class _Nav(NSObject):
    def initWithApp_(self, app):
        self = objc.super(_Nav, self).init()
        if self is None:
            return None
        self._app = weakref.ref(app)
        return self

    def webView_didFinishNavigation_(self, webview, navigation):
        app = self._app()
        if app is not None:
            app.on_js_ready()


class _PopoverDelegate(NSObject):
    def initWithApp_(self, app):
        self = objc.super(_PopoverDelegate, self).init()
        if self is None:
            return None
        self._app = weakref.ref(app)
        return self

    def popoverDidClose_(self, notification):
        app = self._app()
        if app is not None:
            app.on_popover_closed()


class Z407MenuApp:
    def __init__(self):
        self.remote: Z407Remote | None = None
        self.connecting = False
        self.shutting_down = False
        self.js_ready = False
        self.input = "BT"  # 現在入力(取得不可なので既定 BT を保持/ハイライト)
        self.msg = ""
        self._settings = self._load_settings()
        self.lang = self._settings.get("lang", "ja")
        self.bass = self._settings.get("bass", 0)  # ローカル保存値(-5..+5)
        self.spotify_installed = _spotify_installed()
        self._poll_future = None

        self.ns_app = NSApplication.sharedApplication()
        self.ns_app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        # 背景 asyncio ループ
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self._run_loop, daemon=True).start()

        # ステータスアイテム
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self.status_item.button().setTitle_("🔊")
        self._target = _Target.alloc().initWithApp_(self)
        self.status_item.button().setTarget_(self._target)
        self.status_item.button().setAction_("toggle:")

        # WKWebView + メッセージブリッジ
        self._bridge = _Bridge.alloc().initWithApp_(self)
        self._nav = _Nav.alloc().initWithApp_(self)
        self._ucc = WKUserContentController.alloc().init()
        self._ucc.addScriptMessageHandler_name_(self._bridge, "bridge")
        config = WKWebViewConfiguration.alloc().init()
        config.setUserContentController_(self._ucc)
        self.webview = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 0, 384, 540), config
        )
        self.webview.setNavigationDelegate_(self._nav)
        self.webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        try:
            self.webview.setValue_forKey_(False, "drawsBackground")  # 透過
        except Exception:  # noqa: BLE001
            pass
        self.webview.loadHTMLString_baseURL_(HTML, None)

        self._vc = NSViewController.alloc().init()
        self._vc.setView_(self.webview)
        self._pop_delegate = _PopoverDelegate.alloc().initWithApp_(self)
        self.popover = NSPopover.alloc().init()
        self.popover.setContentSize_((384, 540))
        self.popover.setBehavior_(NSPopoverBehaviorTransient)
        self.popover.setContentViewController_(self._vc)
        self.popover.setDelegate_(self._pop_delegate)
        try:
            self.popover.setAppearance_(
                NSAppearance.appearanceNamed_(NSAppearanceNameDarkAqua)
            )
        except Exception:  # noqa: BLE001
            pass

    # --- run loop / lifecycle ---
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self):
        AppHelper.runEventLoop()

    # --- popover ---
    def toggle_popover(self):
        if self.popover.isShown():
            self.popover.performClose_(None)
        else:
            btn = self.status_item.button()
            self.popover.showRelativeToRect_ofView_preferredEdge_(
                btn.bounds(), btn, NSMinYEdge
            )
            self.ns_app.activateIgnoringOtherApps_(True)
            self._start_polling()

    def on_popover_closed(self):
        self._stop_polling()

    def on_js_ready(self):
        self.js_ready = True

    # --- ポーリング(ポップオーバー表示中のみ) ---
    def _start_polling(self):
        if self._poll_future is None or self._poll_future.done():
            self._poll_future = asyncio.run_coroutine_threadsafe(self._poll(), self.loop)

    def _stop_polling(self):
        if self._poll_future is not None:
            self._poll_future.cancel()
            self._poll_future = None

    async def _poll(self):
        while not self.shutting_down:
            state = await self._gather_state()
            self._push_state(state)
            await asyncio.sleep(1.0)

    async def _gather_state(self):
        state = {
            "connected": bool(self.remote and self.remote.connected),
            "connecting": self.connecting,
            "input": self.input,
            "spotifyInstalled": self.spotify_installed,
            "msg": self.msg,
            "lang": self.lang,
            "bass": self.bass,
        }
        vol = await self._osascript(_SYS_VOL_GET)
        try:
            state["volume"] = int(vol)
        except Exception:  # noqa: BLE001
            pass
        if self.spotify_installed:
            raw = await self._osascript(_SPOTIFY_STATE)
            f = raw.split("~|~")
            if len(f) == 6 and f[0] == "1":
                state["spotify"] = True
                state["playing"] = f[1] == "playing"
                state["title"] = f[2]
                state["artist"] = f[3]
                try:
                    state["position"] = float(f[4])
                except Exception:  # noqa: BLE001
                    state["position"] = 0
                try:
                    state["duration"] = float(f[5])
                except Exception:  # noqa: BLE001
                    state["duration"] = 0
            else:
                state["spotify"] = False
        else:
            state["spotify"] = False
        return state

    def _push_state(self, state):
        if self.shutting_down or not self.js_ready:
            return
        AppHelper.callAfter(self._eval, "applyState(" + json.dumps(state) + ")")

    def _eval(self, js):  # メインスレッド
        if self.shutting_down or self.webview is None:
            return
        try:
            self.webview.evaluateJavaScript_completionHandler_(js, None)
        except Exception:  # noqa: BLE001
            pass

    # --- アクション(メインスレッド: ブリッジから呼ばれる) ---
    def on_action(self, action, value):
        if action == "connect":
            self._do_connect()
        elif action == "play":
            self._submit(self._spotify_cmd(_SP_PLAYPAUSE))
        elif action == "prev":
            self._submit(self._spotify_cmd(_SP_PREV))
        elif action == "next":
            self._submit(self._spotify_cmd(_SP_NEXT))
        elif action == "volume":
            try:
                v = int(value)
            except Exception:  # noqa: BLE001
                return
            self._submit(self._set_volume(v))
        elif action == "input":
            self._set_input(str(value))
        elif action == "pair":
            if self._require_connected():
                self._submit(self.remote.bluetooth_pair())
        elif action == "bassUp":
            if self._require_connected():
                self._submit(self.remote.bass_up())
        elif action == "bassDown":
            if self._require_connected():
                self._submit(self.remote.bass_down())
        elif action == "bass":
            # 画面のバス推定値をローカル保存用に受け取る(実機の値ではない点に注意)。
            try:
                v = int(value)
            except Exception:  # noqa: BLE001
                return
            self.bass = max(-5, min(5, v))
            self._save_settings()
        elif action == "spotifyOpen":
            self._submit(self._spotify_open())
        elif action == "factoryReset":
            if self._require_connected():
                self._submit(self._factory_reset())
        elif action == "connectAndReset":
            self._do_connect_and_reset()
        elif action == "connectAndPair":
            self._do_connect_and_pair()
        elif action == "size":
            self._resize_popover(value)
        elif action == "setLang":
            if value in ("ja", "en"):
                self.lang = value
                self._save_lang()
                # 即時反映: 現在の基本状態を送り直す
                self._push_state({
                    "connected": bool(self.remote and self.remote.connected),
                    "connecting": self.connecting,
                    "input": self.input,
                    "spotifyInstalled": self.spotify_installed,
                    "msg": self.msg,
                    "lang": self.lang,
                })
        elif action == "quit":
            self.quit()

    def _resize_popover(self, value):
        try:
            h = int(value)
        except Exception:  # noqa: BLE001
            return
        h = max(120, min(900, h))
        # ブリッジはメインスレッド。contentSize 変更で WebView は autoresize により追従する。
        self.popover.setContentSize_((384, h))

    def _require_connected(self) -> bool:
        if not (self.remote and self.remote.connected):
            self.msg = self._T("notConnected")
            return False
        return True

    def _scan_hint(self, attempt: int) -> str:
        """スキャンで何度も見つからない場合に付ける復旧ヒント。

        Z407 は Factory Reset 後に BLE 広告を止めることがあり、その間は
        何度スキャンしても見つからない(アプリは正常)。その際の対処を表示する。
        """
        if attempt < 3:
            return ""
        return self._T("searchHint")

    # --- 設定(i18n / bass) ---
    def _load_settings(self) -> dict:
        """settings.json を読み、全キー(lang, bass)を返す。欠落・不正なら既定値。"""
        s = {"lang": "ja", "bass": 0}
        try:
            with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("lang", "ja")
            if lang in ("ja", "en"):
                s["lang"] = lang
            b = data.get("bass", 0)
            if isinstance(b, (int, float)):
                s["bass"] = max(-5, min(5, int(b)))
        except Exception:  # noqa: BLE001
            pass
        return s

    def _save_settings(self) -> None:
        """settings.json に現在の設定(lang, bass)を保存する。ディレクトリも保証。"""
        try:
            os.makedirs(os.path.dirname(_SETTINGS_FILE), exist_ok=True)
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({"lang": self.lang, "bass": self.bass}, f, ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass

    def _load_lang(self) -> str:
        """永続化した言語設定(self._settings の lang)を返す。なければ日本語。"""
        return self._settings.get("lang", "ja")

    def _save_lang(self) -> None:
        self._save_settings()

    def _T(self, key: str, **kw) -> str:
        """現在の言語でメッセージを取得する。見つからなければ日本語、それも無ければ key。"""
        text = _MSG.get(self.lang, {}).get(key) or _MSG["ja"].get(key, key)
        try:
            return text.format(**kw)
        except Exception:  # noqa: BLE001
            return text

    def _do_connect(self):
        if self.connecting:
            # 再試行中にもう一度押されたら中止(self.connecting を倒すとループが抜ける)
            self.connecting = False
            self.msg = self._T("cancelReconnect")
            return
        self.connecting = True
        self.msg = ""
        self._submit(self._connect())

    async def _connect(self):
        # 元 Windows アプリと同様、見つかるまでスキャンを繰り返す(中止可能)。
        try:
            st = _bluetooth_status()
            if st in ("denied", "restricted"):
                self.msg = self._T("btDenied")
                return
            attempt = 0
            remote = None
            while self.connecting and remote is None:
                attempt += 1
                self.msg = self._T("searching", attempt=attempt) + self._scan_hint(attempt)
                remote = await Z407Remote.find(timeout=8.0)
                if remote is None:
                    if st == "notdetermined":
                        self.msg = self._T("btApprove")
                    if self.connecting:
                        await asyncio.sleep(1.0)  # 少し待って再スキャン
            if not self.connecting or remote is None:
                return  # 中止された
            self.msg = self._T("connecting")
            await remote.connect()
            remote.on_input_change = self._on_input_actual
            self.remote = remote
            self.msg = ""
        except Exception as e:  # noqa: BLE001
            m = str(e).lower()
            if any(k in m for k in ("authoriz", "powered", "turned off", "permission", "not allowed")):
                self.msg = self._T("btNeedPerm")
            else:
                self.msg = self._T("connectFail", err=e)
        finally:
            self.connecting = False

    def _do_connect_and_reset(self):
        # 未接続でも使える「接続して即 factory reset」。詰み回避用。
        if self.connecting:
            self.connecting = False  # 進行中なら中止
            self.msg = self._T("cancelled")
            return
        self.connecting = True
        self.msg = ""
        self._submit(self._connect_and_reset())

    async def _connect_and_reset(self):
        try:
            st = _bluetooth_status()
            if st in ("denied", "restricted"):
                self.msg = self._T("btDenied")
                return
            attempt = 0
            remote = None
            while self.connecting and remote is None:
                attempt += 1
                self.msg = self._T("resettingFor", attempt=attempt) + self._scan_hint(attempt)
                remote = await Z407Remote.find(timeout=8.0)
                if remote is None and self.connecting:
                    await asyncio.sleep(1.0)
            if not self.connecting or remote is None:
                return
            await remote.connect()
            if not self.connecting:
                # 接続中にキャンセルされた場合は Factory Reset を送らない
                await remote.disconnect()
                return
            try:
                await remote.factory_reset()
                # 送信が成功して初めて成功メッセージを表示する
                self.msg = self._T("resetSent")
            except Exception as e:  # noqa: BLE001
                # 書き込み自体が失敗した場合はエラー表示
                self.msg = self._T("resetFail", err=e)
        except Exception as e:  # noqa: BLE001
            self.msg = self._T("resetFail", err=e)
        finally:
            self.connecting = False
            self.remote = None

    def _do_connect_and_pair(self):
        # 未接続でも使える「接続してペアリングモード送信」。
        if self.connecting:
            self.connecting = False  # 進行中なら中止
            self.msg = self._T("cancelled")
            return
        self.connecting = True
        self.msg = ""
        self._submit(self._connect_and_pair())

    async def _connect_and_pair(self):
        try:
            st = _bluetooth_status()
            if st in ("denied", "restricted"):
                self.msg = self._T("btDenied")
                return
            attempt = 0
            remote = None
            while self.connecting and remote is None:
                attempt += 1
                self.msg = self._T("pairingFor", attempt=attempt) + self._scan_hint(attempt)
                remote = await Z407Remote.find(timeout=8.0)
                if remote is None and self.connecting:
                    await asyncio.sleep(1.0)
            if not self.connecting or remote is None:
                return
            await remote.connect()
            if not self.connecting:
                # 接続中にキャンセルされた場合は Pair を送らない
                await remote.disconnect()
                return
            remote.on_input_change = self._on_input_actual
            self.remote = remote  # ペアリングでは接続は維持される
            await remote.bluetooth_pair()
            self.msg = self._T("pairSent")
        except Exception as e:  # noqa: BLE001
            self.msg = self._T("pairFail", err=e)
        finally:
            self.connecting = False

    def _set_input(self, which):
        if not self._require_connected():
            return
        coro = {
            "BT": self.remote.input_bluetooth,
            "AUX": self.remote.input_aux,
            "USB": self.remote.input_usb,
        }.get(which)
        if coro:
            self.input = which
            self._submit(coro())

    def _on_input_actual(self, which):
        """実機の入力切替通知(cf04/05/06)を反映する。

        z407_remote の notify コールバック(asyncio ループ)から呼ばれる。
        ここでは self.input を更新するだけにし、即時 push はしない。次のポーリング
        (_gather_state)がフル状態を送るため、部分状態 push による Spotify 表示への
        影響を避けつつ 1s 以内に JS 側へ反映される。self.input への書き込みは
        _gather_state と同じ asyncio ループから行われるため競合しない。
        """
        if which in ("BT", "AUX", "USB"):
            self.input = which

    async def _set_volume(self, v):
        v = max(0, min(100, int(v)))
        await self._osascript("set volume output volume " + str(v))

    async def _spotify_cmd(self, script):
        if not await self._osascript(script):
            self.msg = self._T("spotifyErr")

    async def _factory_reset(self):
        # 8300 を送ると Z407 が全ペアリングを消して再起動する(=接続も切れる)。
        try:
            await self.remote.factory_reset()
            # 送信が成功して初めて成功メッセージを表示する
            self.msg = self._T("resetSent")
        except Exception as e:  # noqa: BLE001
            # 書き込み自体が失敗した場合はエラー表示
            self.msg = self._T("resetFail", err=e)
        finally:
            self.remote = None

    async def _spotify_open(self):
        if not self.spotify_installed:
            self.msg = self._T("spotifyNotInstalled")
            return
        try:
            proc = await asyncio.create_subprocess_exec("open", "-a", "Spotify")
            await asyncio.wait_for(proc.communicate(), timeout=5.0)
        except Exception:  # noqa: BLE001
            pass

    # --- 共通 ---
    def _submit(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def _done(f):
            try:
                f.result()
            except Exception as e:  # noqa: BLE001
                self.msg = self._T("errPrefix", err=e)

        fut.add_done_callback(_done)
        return fut

    async def _osascript(self, script: str) -> str:
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return out.decode("utf-8", "replace").strip()
        except Exception:  # noqa: BLE001
            if proc is not None:
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            return ""

    # --- 終了 ---
    def quit(self):
        self.shutting_down = True
        self._stop_polling()
        try:
            self._ucc.removeScriptMessageHandlerForName_("bridge")
        except Exception:  # noqa: BLE001
            pass

        async def _sd():
            if self.remote:
                try:
                    await self.remote.disconnect()
                except Exception:  # noqa: BLE001
                    pass

        try:
            fut = asyncio.run_coroutine_threadsafe(_sd(), self.loop)
            fut.result(timeout=3)
        except Exception:  # noqa: BLE001
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.ns_app.terminate_(None)


if __name__ == "__main__":
    Z407MenuApp().run()
