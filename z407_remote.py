"""Logitech Z407 スピーカーを BLE で制御するロジック。

Logitech Z407 の BLE / GATT プロトコルを調査し、macOS (CoreBluetooth) で
動くよう bleak を使って独立して実装したもの。GUI は含まない。
"""

import asyncio

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# Z407 の GATT 定義(プロトコル調査で判明した値)
SERVICE_UUID = "0000fdc2-0000-1000-8000-00805f9b34fb"
COMMAND_UUID = "c2e758b9-0e78-41e0-b0cb-98a593193fc5"  # write (response 不要)
RESPONSE_UUID = "b84ac9c6-29c5-46d4-bba1-9d534784330f"  # notify

# 接続ハンドシェイク中にデバイスから notify されるマーカー
_HS_REQUEST = b"\xd4\x05\x01"  # 「ACK を返せ」
_HS_DONE = b"\xd4\x00\x01"     # 「接続確立」

# 入力が実際に切り替わったときにデバイスから notify されるステータス(freundTech の
# Protocol.md で判明したレスポンスコード)。cf04=BT / cf05=AUX / cf06=USB。
_INPUT_STATUS = {
    b"\xcf\x04": "BT",
    b"\xcf\x05": "AUX",
    b"\xcf\x06": "USB",
}

# コマンド(hex 文字列 → bytes.fromhex で送信)
_CMD_CONNECT = "8405"
_CMD_HANDSHAKE_ACK = "8400"
_CMD_BASS_UP = "8000"
_CMD_BASS_DOWN = "8001"
_CMD_VOLUME_UP = "8002"
_CMD_VOLUME_DOWN = "8003"
_CMD_PLAY_PAUSE = "8004"
_CMD_INPUT_BLUETOOTH = "8101"
_CMD_INPUT_AUX = "8102"
_CMD_INPUT_USB = "8103"
_CMD_BLUETOOTH_PAIR = "8200"
_CMD_FACTORY_RESET = "8300"


class Z407Remote:
    """1 台の Z407 への接続とコマンド送信を担う。

    bleak のオブジェクト生成・接続・通信はすべて背景 asyncio ループ上で
    行う前提(rumps のメインスレッドからは run_coroutine_threadsafe 経由)。
    """

    def __init__(self, device: BLEDevice):
        self._device = device
        self.client: BleakClient | None = None
        self.connected = False
        self._handshake: asyncio.Event | None = None
        self.on_input_change = None  # 入力切替通知先(str "BT"/"AUX"/"USB" を受ける callable)

    @staticmethod
    async def find(timeout: float = 12.0) -> "Z407Remote | None":
        """SERVICE_UUID を広告している Z407 を 1 台探す。見つからなければ None。"""
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: SERVICE_UUID.lower()
            in [u.lower() for u in ad.service_uuids],
            timeout=timeout,
            service_uuids=[SERVICE_UUID],  # macOS では指定しないと拾えないことがある
        )
        return Z407Remote(device) if device else None

    async def connect(self, handshake_timeout: float = 8.0) -> None:
        """接続してハンドシェイクを完了させる。失敗時は切断して例外を送出。

        手順: connect → start_notify → "8405" 送信
        → デバイスが d4 05 01 → こちらが "8400" → デバイスが d4 00 01 で確立。
        """
        self._handshake = asyncio.Event()
        self.client = BleakClient(self._device, disconnected_callback=self._on_disconnected)
        await self.client.connect()
        try:
            await self.client.start_notify(RESPONSE_UUID, self._on_notify)
            await self._write(_CMD_CONNECT)
            await asyncio.wait_for(self._handshake.wait(), timeout=handshake_timeout)
        except Exception:
            await self.disconnect()
            raise
        self.connected = True

    def _on_disconnected(self, _client) -> None:
        """自発切断(電源断・通信範囲外など)を検知して接続状態を更新する。

        このコールバックは bleak の内部ループから呼ばれる。`disconnect()`
        を明示的に呼んだ場合もここに来るため、ここではフラグだけ落とす。
        """
        self.connected = False

    async def disconnect(self) -> None:
        self.connected = False
        if self.client is not None:
            try:
                await self.client.disconnect()
            finally:
                self.client = None

    async def _on_notify(self, _sender, data: bytearray) -> None:
        data = bytes(data)
        if data == _HS_REQUEST:
            await self._write(_CMD_HANDSHAKE_ACK)
        elif data == _HS_DONE and self._handshake is not None:
            self._handshake.set()
        else:
            src = _INPUT_STATUS.get(data)
            if src is not None and self.on_input_change is not None:
                self.on_input_change(src)

    async def _write(self, command_hex: str) -> None:
        """生のコマンド送信。接続ガードはしない(ハンドシェイク中も使うため)。"""
        await self.client.write_gatt_char(
            COMMAND_UUID, bytes.fromhex(command_hex), response=False
        )

    # --- 公開コマンド(接続済みかの確認は呼び出し側=アプリ層で行う) ---
    async def bass_up(self) -> None:
        """Bass(低音)を一段上げる(一方向コマンド。現在値の取得は不可)。"""
        await self._write(_CMD_BASS_UP)

    async def bass_down(self) -> None:
        """Bass(低音)を一段下げる(一方向コマンド。現在値の取得は不可)。"""
        await self._write(_CMD_BASS_DOWN)

    async def volume_up(self) -> None:
        await self._write(_CMD_VOLUME_UP)

    async def volume_down(self) -> None:
        await self._write(_CMD_VOLUME_DOWN)

    async def play_pause(self) -> None:
        await self._write(_CMD_PLAY_PAUSE)

    async def input_bluetooth(self) -> None:
        await self._write(_CMD_INPUT_BLUETOOTH)

    async def input_aux(self) -> None:
        await self._write(_CMD_INPUT_AUX)

    async def input_usb(self) -> None:
        await self._write(_CMD_INPUT_USB)

    async def bluetooth_pair(self) -> None:
        await self._write(_CMD_BLUETOOTH_PAIR)

    async def factory_reset(self) -> None:
        await self._write(_CMD_FACTORY_RESET)
