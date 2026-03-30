#!/bin/bash
# Refresh XHS login via QR scan
# Usage: bash xhs-refresh-login.sh
# This opens a QR code — scan with 小红书 app to refresh cookies.
# Cookies persist in ~/.agent-reach/tools/xiaohongshu-mcp/cookies.json
# Typically lasts 30-365 days depending on the cookie.

set -e
XHS_DIR="$HOME/.agent-reach/tools/xiaohongshu-mcp"
LOGIN_BIN="$XHS_DIR/xiaohongshu-login-darwin-arm64"

if [ ! -f "$LOGIN_BIN" ]; then
  echo "❌ Login tool not found: $LOGIN_BIN"
  exit 1
fi

echo "📱 正在打开小红书扫码登录..."
echo "   扫码后 cookie 自动保存到 $XHS_DIR/cookies.json"
echo "   Cookie 有效期通常 30-365 天"
echo ""

cd "$XHS_DIR"
"$LOGIN_BIN"

echo ""
echo "✅ 登录完成！Cookie 已更新。"
echo "   运行 omnifeed fetch 验证小红书是否可用。"
