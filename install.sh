#!/bin/bash
# Z407 Remote (macOS 版) インストーラ
#   - ランタイム(.venv + スクリプト)を内蔵ディスクの Application Support に配置
#   - py2app(alias モード)で "Z407 Remote.app" を生成し /Applications へ
#     (/Applications に書き込めない場合は ~/Applications)
#
# なぜ py2app か:
#   .app のランチャーで外部の python を exec すると、実行中アプリの identity が
#   org.python.python になり、Info.plist(LSUIElement / Bluetooth 使用許可文)が
#   無視される。結果、メニューバーにアイコンが出ない & Bluetooth 使用時に
#   macOS がアプリを強制終了する。py2app は identity を com.local.z407remote に
#   する正しいバンドルを作る。alias モードなのでこの Mac の venv を参照する。
#
# なぜ内蔵ディスクか:
#   外部ボリューム(/Volumes/...)上のファイルは LaunchServices 起動アプリから
#   TCC で読めない。ソースはこのリポジトリ、実体は内蔵ディスクへ配置する。
#
# このリポジトリは「ソース」。編集したら再度 install.sh を実行して反映する。
# sudo 不要。再実行しても安全(冪等)。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# --- 既存アプリを安全に停止する(完全一致 PID 特定) ---
# 対象アプリの実行ファイル絶対パスに完全一致するプロセスだけを TERM する。
# 似た名前の無関係プロセスは終了しない。終了待ちは上限付きで、タイムアウト時は
# 既存アプリを削除せずエラー終了する。
stop_app() {
    local app_path="$1"
    [ -n "$app_path" ] || return 0
    # 実行ファイル絶対パスを正規表現からエスケープして、完全一致で PID を特定する
    local pattern
    pattern="$(printf '%s' "$app_path" | sed 's/[][\.^$*+?{}\|()]/\\&/g')"
    local pids
    pids="$(pgrep -f "^${pattern}\$" 2>/dev/null || true)"
    [ -n "$pids" ] || { echo "  (実行中のアプリはありません)"; return 0; }
    echo "  -> 停止対象 PID: $pids"
    # TERM 送信。失敗時は「既に消えた」場合のみ正常扱い、権限エラー等は中止する。
    for pid in $pids; do
        if ! kill -TERM "$pid" 2>/dev/null; then
            # PID が既に存在しない場合は正常(対象は消えた)
            if kill -0 "$pid" 2>/dev/null; then
                echo "エラー: PID $pid を停止できませんでした(権限/プロセス状態)。中止します。" >&2
                exit 1
            fi
        fi
    done
    # 終了待ち(上限 5 秒)
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
    echo "エラー: 既存アプリが終了しませんでした(5 秒)。既存アプリを削除せず中止します。" >&2
    exit 1
}

# Python 3.12 を用意(無ければ Homebrew で導入)。
# bleak/pyobjc の arm64 wheel と本コードの型注釈(PEP 604)に 3.12+ が前提。
if [ -z "${PYTHON:-}" ] && ! command -v python3.12 >/dev/null 2>&1; then
    echo "==> Python 3.12 が見つかりません"
    if command -v brew >/dev/null 2>&1; then
        echo "==> Homebrew で python@3.12 を導入します"
        brew install python@3.12
        export PATH="$(brew --prefix)/bin:$PATH"
    else
        echo "Homebrew が無いため Python 3.12 を自動導入できません。導入後に再実行してください:"
        echo "  - Homebrew: https://brew.sh を入れて 'brew install python@3.12'"
        echo "  - または python.org から Python 3.12: https://www.python.org/downloads/"
        exit 1
    fi
fi
PYTHON="${PYTHON:-$(command -v python3.12)}"
echo "==> Using Python: $PYTHON ($($PYTHON --version 2>&1))"

RUNTIME="$HOME/Library/Application Support/Z407 Remote"

# インストール先を決め、実行中の既存アプリを停止する($RUNTIME 上書きより先に行う)。
DEST_DIR="/Applications"
if [ ! -w "$DEST_DIR" ]; then
    DEST_DIR="$HOME/Applications"
    mkdir -p "$DEST_DIR"
fi
APP="$DEST_DIR/Z407 Remote.app"
EXEC_PATH="$APP/Contents/MacOS/Z407 Remote"
echo "==> 既存アプリを停止します: $APP"
stop_app "$EXEC_PATH"

echo "==> Deploying runtime to: $RUNTIME"
mkdir -p "$RUNTIME"
cp z407_app.py z407_remote.py panel.py requirements.txt setup.py "$RUNTIME/"
mkdir -p "$RUNTIME/assets"
cp assets/Z407Remote.icns "$RUNTIME/assets/"

if [ ! -x "$RUNTIME/.venv/bin/python" ]; then
    echo "==> Creating virtualenv"
    "$PYTHON" -m venv "$RUNTIME/.venv"
    "$RUNTIME/.venv/bin/python" -m pip install --quiet --upgrade pip
fi
echo "==> Installing dependencies (bleak, pyobjc-WebKit, py2app)"
"$RUNTIME/.venv/bin/pip" install --quiet -r "$RUNTIME/requirements.txt" py2app

echo "==> Building 'Z407 Remote.app' with py2app (alias mode)"
cd "$RUNTIME"
rm -rf build dist
"$RUNTIME/.venv/bin/python" setup.py py2app -A >/tmp/z407_py2app.log 2>&1 || {
    echo "py2app build failed. See /tmp/z407_py2app.log"; tail -20 /tmp/z407_py2app.log; exit 1;
}

DEST_DIR="/Applications"
if [ ! -w "$DEST_DIR" ]; then
    DEST_DIR="$HOME/Applications"
    mkdir -p "$DEST_DIR"
fi
APP="$DEST_DIR/Z407 Remote.app"
echo "==> Installing app to $APP"
# 既に冒頭で停止済み(確認用に再停止しても安全)
stop_app "$APP/Contents/MacOS/Z407 Remote"
rm -rf "$APP"
ditto "$RUNTIME/dist/Z407 Remote.app" "$APP"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" 2>/dev/null || true

echo ""
echo "==> 起動します"
open "$APP"
echo ""
echo "==> Done."
echo "    メニューバー右側に 🔊 アイコンが出ます(Spotlight で 'Z407 Remote' でも起動可)。"
echo "    初回の Connect 時に Bluetooth の許可ダイアログ(\"Z407 Remote\")→ 許可。"
echo "    Spotify 操作時はオートメーション許可 → 許可。"
echo "    出ない/拒否した場合: システム設定 → プライバシーとセキュリティ から許可。"
