#!/bin/bash
# 別の Mac(自分用・Apple Silicon)で Z407 Remote をインストールするスクリプト。
#   - 同じフォルダの "Z407 Remote.app"(無ければ ~/Downloads の zip)を
#     /Applications(不可なら ~/Applications)へインストール
#   - Gatekeeper の隔離属性を除去し、アドホック署名し直して、起動する
#
# 使い方(どちらでも):
#   A) このファイルを右クリック →「開く」→「開く」
#   B) ターミナルで:  bash "<このファイルのパス>"
set -e

SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
APPNAME="Z407 Remote.app"

echo "== Z407 Remote インストーラ =="

# 1) アプリの場所を特定
SRC=""
if [ -d "$SELF_DIR/$APPNAME" ]; then
    SRC="$SELF_DIR/$APPNAME"
else
    for z in "$SELF_DIR/Z407-Remote-macos.zip" "$HOME/Downloads/Z407-Remote-macos.zip"; do
        if [ -f "$z" ]; then
            TMP="$(mktemp -d)"
            ditto -xk "$z" "$TMP"
            SRC="$(/usr/bin/find "$TMP" -maxdepth 3 -name "$APPNAME" -type d | head -1)"
            break
        fi
    done
fi
if [ -z "$SRC" ] || [ ! -d "$SRC" ]; then
    echo "エラー: \"$APPNAME\" が見つかりません。"
    echo "       このスクリプトと同じフォルダにアプリ(または zip)を置いてください。"
    exit 1
fi

# 2) インストール先(/Applications が書ければそこ、無理なら ~/Applications)
DEST_DIR="/Applications"
if touch "$DEST_DIR/.z407w" 2>/dev/null; then
    rm -f "$DEST_DIR/.z407w"
else
    DEST_DIR="$HOME/Applications"
    mkdir -p "$DEST_DIR"
fi
DEST="$DEST_DIR/$APPNAME"
echo "==> インストール先: $DEST"

# 3) 既存アプリを安全に停止してから置き換える
stop_app() {
    local app_path="$1"
    [ -n "$app_path" ] || return 0
    local pattern
    pattern="$(printf '%s' "$app_path" | sed 's/[][\.^$*+?{}\|()]/\\&/g')"
    local pids
    pids="$(pgrep -f "^${pattern}\$" 2>/dev/null || true)"
    [ -n "$pids" ] || return 0
    echo "  -> 停止対象 PID: $pids"
    for pid in $pids; do
        if ! kill -TERM "$pid" 2>/dev/null; then
            if kill -0 "$pid" 2>/dev/null; then
                echo "エラー: PID $pid を停止できませんでした。中止します。" >&2
                exit 1
            fi
        fi
    done
    local waited=0
    while [ $waited -lt 50 ]; do
        local remaining=""
        for pid in $pids; do
            if kill -0 "$pid" 2>/dev/null; then remaining="$remaining $pid"; fi
        done
        if [ -z "$remaining" ]; then echo "  -> 停止を確認しました。"; return 0; fi
        sleep 0.1
        waited=$((waited + 1))
    done
    echo "エラー: 既存アプリが終了しませんでした(5 秒)。削除せず中止します。" >&2
    exit 1
}
stop_app "$DEST/Contents/MacOS/Z407 Remote"

[ -d "$DEST" ] && rm -rf "$DEST"
cp -R "$SRC" "$DEST_DIR/"

# 4) Gatekeeper 隔離属性を除去 + アドホック署名し直し
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
codesign --force --deep -s - "$DEST" >/dev/null 2>&1 || true

# 5) 起動
open "$DEST"
echo "==> 完了。メニューバー右側の 🔊 を確認してください。"
echo "    初回操作時に Bluetooth / Spotify(オートメーション)の許可を承認してください。"
