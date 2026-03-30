#!/usr/bin/env python3
"""Bilibili QR login — scan once, cookies persist for months.

Usage: python3 bili-login.py
  1. Opens QR code in browser
  2. Scan with Bilibili app
  3. Cookies saved to ~/.omnifeed/bilibili_cookies.json

Cookie SESSDATA typically lasts 6+ months.
"""

import httpx
import json
import time
import sys
import os
import subprocess
import tempfile

COOKIE_PATH = os.path.expanduser("~/.omnifeed/bilibili_cookies.json")
QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


def generate_qr():
    r = httpx.get(QR_GENERATE, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    data = r.json()
    if data.get("code") != 0:
        print(f"Failed to generate QR: {data}")
        sys.exit(1)
    return data["data"]["url"], data["data"]["qrcode_key"]


def show_qr(url: str):
    """Show QR code — try terminal first, fallback to browser."""
    # Try qrencode CLI
    try:
        subprocess.run(["qrencode", "-t", "UTF8", url], check=True)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Fallback: open QR image in browser via API
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url}"
    print(f"\n📱 扫描二维码登录 Bilibili\n")
    print(f"QR 图片: {qr_url}\n")

    # Also create local HTML
    html = f"""<html><body style="display:flex;justify-content:center;align-items:center;height:100vh;background:#f5f5f7;font-family:system-ui">
    <div style="text-align:center"><h2>扫码登录 Bilibili</h2>
    <img src="{qr_url}" style="border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
    <p style="color:#666;margin-top:16px">打开 Bilibili App 扫描二维码</p></div></body></html>"""
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    tmp.write(html.encode())
    tmp.close()
    subprocess.run(["open", tmp.name])


def poll_login(qrcode_key: str, timeout: int = 120) -> dict:
    """Poll login status until success or timeout."""
    client = httpx.Client(timeout=10)
    start = time.time()

    while time.time() - start < timeout:
        r = client.get(QR_POLL, params={"qrcode_key": qrcode_key},
                       headers={"User-Agent": "Mozilla/5.0"})
        data = r.json().get("data", {})
        code = data.get("code", -1)

        if code == 0:
            # Success! Extract cookies from response
            print("\n✅ 登录成功！")
            cookies = dict(client.cookies)
            # Also extract from Set-Cookie in redirect
            refresh_token = data.get("refresh_token", "")
            url = data.get("url", "")
            if url:
                # Follow the redirect to get all cookies
                r2 = client.get(url, follow_redirects=True)
                cookies.update(dict(client.cookies))
            return {"cookies": cookies, "refresh_token": refresh_token}

        elif code == 86038:
            print("❌ 二维码已过期，请重新运行")
            sys.exit(1)
        elif code == 86090:
            print("📱 已扫码，请在手机上确认...", end="\r")
        elif code == 86101:
            pass  # Waiting for scan
        else:
            print(f"Unknown status: {code}")

        time.sleep(2)

    print("\n⏰ 超时，请重试")
    sys.exit(1)


def save_cookies(login_data: dict):
    os.makedirs(os.path.dirname(COOKIE_PATH), exist_ok=True)
    with open(COOKIE_PATH, "w") as f:
        json.dump(login_data, f, indent=2)
    print(f"💾 Cookies 已保存到 {COOKIE_PATH}")

    # Show key info
    cookies = login_data.get("cookies", {})
    mid = cookies.get("DedeUserID", "?")
    sessdata = cookies.get("SESSDATA", "")
    print(f"   用户 ID: {mid}")
    print(f"   SESSDATA: {sessdata[:20]}...")


def main():
    print("🎮 Bilibili 扫码登录\n")

    # Check if already logged in
    if os.path.exists(COOKIE_PATH):
        with open(COOKIE_PATH) as f:
            existing = json.load(f)
        mid = existing.get("cookies", {}).get("DedeUserID", "")
        if mid:
            print(f"已有登录 cookie (UID: {mid})")
            ans = input("重新登录? (y/N): ").strip().lower()
            if ans != "y":
                print("保持现有登录")
                return

    url, key = generate_qr()
    show_qr(url)
    print("等待扫码...")

    login_data = poll_login(key)
    save_cookies(login_data)

    # Test: get user favorites
    print("\n🔍 测试获取收藏夹...")
    cookies = login_data["cookies"]
    mid = cookies.get("DedeUserID", "")
    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())

    r = httpx.get(
        "https://api.bilibili.com/x/v3/fav/folder/created/list-all",
        params={"up_mid": mid},
        headers={"User-Agent": "Mozilla/5.0", "Cookie": cookie_str},
        timeout=10,
    )
    data = r.json()
    if data.get("code") == 0:
        folders = data.get("data", {}).get("list", [])
        print(f"收藏夹: {len(folders)} 个")
        for folder in folders[:5]:
            print(f"  📁 {folder['title']} ({folder['media_count']} 个视频)")
    else:
        print(f"获取收藏夹失败: {data.get('message', '')}")


if __name__ == "__main__":
    main()
