#!/bin/bash
# 自己完結(standalone)アプリをビルドして配布用 zip を作る。
#   - Python・bleak・pyobjc・WebKit を全部 .app に同梱(venv 不要・単体で動く)
#   - 自分の別の Mac(Apple Silicon)へコピーして使う用途。Apple 公証はしない。
#
# 前提: 先に install.sh を一度実行して依存入りの venv を用意しておくこと
# (ビルドにはその venv の python と py2app を使う)。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PY="$HOME/Library/Application Support/Z407 Remote/.venv/bin/python"
[ -x "$PY" ] || { echo "先に 'bash install.sh' を実行して venv を作成してください"; exit 1; }

echo "==> standalone ビルド(数分かかる場合あり)"
rm -rf build dist
"$PY" setup.py py2app >/tmp/z407_package.log 2>&1 || {
    echo "ビルド失敗。ログ: /tmp/z407_package.log"; tail -25 /tmp/z407_package.log; exit 1;
}

echo "==> アドホック署名(Apple Silicon で起動可能にする)"
codesign --force --deep -s - "dist/Z407 Remote.app" 2>&1 || { echo "署名失敗。中止します。"; exit 1; }

echo "==> 署名検証"
codesign --verify --deep --strict --verbose=2 "dist/Z407 Remote.app" 2>&1 || { echo "署名検証失敗。中止します。"; exit 1; }

echo "==> 配布フォルダ(アプリ + インストーラ)を作成して zip 化"
PKG="dist/Z407 Remote"
rm -rf "$PKG"; mkdir -p "$PKG"
mv "dist/Z407 Remote.app" "$PKG/"
cp install.command "$PKG/install.command"
chmod +x "$PKG/install.command"
( cd dist && ditto -c -k --sequesterRsrc --keepParent "Z407 Remote" "Z407-Remote-macos.zip" )
cp "dist/Z407-Remote-macos.zip" "$HOME/Downloads/Z407-Remote-macos.zip" 2>/dev/null || true

echo ""
echo "==> 完成"
echo "    配布 zip: $DIR/dist/Z407-Remote-macos.zip  (~/Downloads にもコピー済み)"
echo "    中身: Z407 Remote.app + install.command(自動インストーラ)"
echo ""
echo "別 Mac(Apple Silicon)での導入:"
echo "  1. zip を AirDrop でコピーして展開"
echo "  2. ターミナルで:  bash ~/Downloads/Z407-Remote-macos.zip を展開したフォルダの install.command"
echo "     または install.command を右クリック → 開く → 開く"
echo "  3. 自動で /Applications へ入り、隔離解除して起動します"
