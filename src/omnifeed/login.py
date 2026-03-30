"""Login/auth module for OmniFeed platforms.

Provides:
  login_bilibili()    — QR scan flow (ported from scripts/bili-login.py)
  login_github()      — gh CLI or personal access token
  verify_api_key()    — test LLM API key with a minimal request
  auto_build_profile()— build profile from all available authenticated sources
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console

console = Console()

COOKIE_PATH = Path("~/.omnifeed/bilibili_cookies.json").expanduser()
QR_GENERATE = "https://passport.bilibili.com/x/passport-login/web/qrcode/generate"
QR_POLL = "https://passport.bilibili.com/x/passport-login/web/qrcode/poll"


# ── Bilibili ──────────────────────────────────────────────────────────────────

def _bili_generate_qr() -> tuple[str, str]:
    """Request a new Bilibili QR code. Returns (url, qrcode_key)."""
    r = httpx.get(QR_GENERATE, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Failed to generate QR: {data}")
    return data["data"]["url"], data["data"]["qrcode_key"]


def _bili_show_qr(url: str) -> None:
    """Render QR code — try terminal (qrencode), fall back to browser."""
    try:
        subprocess.run(["qrencode", "-t", "UTF8", url], check=True)
        return
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Fallback: open HTML page in browser
    qr_img = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={url}"
    console.print(f"\n  QR image: {qr_img}\n")
    html = (
        "<html><body style=\"display:flex;justify-content:center;align-items:center;"
        "height:100vh;background:#f5f5f7;font-family:system-ui\">"
        "<div style=\"text-align:center\"><h2>扫码登录 Bilibili</h2>"
        f"<img src=\"{qr_img}\" style=\"border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1)\">"
        "<p style=\"color:#666;margin-top:16px\">打开 Bilibili App 扫描二维码</p></div></body></html>"
    )
    tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)
    tmp.write(html.encode())
    tmp.close()
    try:
        subprocess.run(["open", tmp.name])
    except FileNotFoundError:
        try:
            subprocess.run(["xdg-open", tmp.name])
        except FileNotFoundError:
            console.print(f"  Open this file in your browser: {tmp.name}")


def _bili_poll(qrcode_key: str, timeout: int = 120) -> dict:
    """Poll QR status. Returns login_data dict on success, raises on failure."""
    client = httpx.Client(timeout=10)
    start = time.time()

    while time.time() - start < timeout:
        r = client.get(
            QR_POLL,
            params={"qrcode_key": qrcode_key},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        data = r.json().get("data", {})
        code = data.get("code", -1)

        if code == 0:
            cookies = dict(client.cookies)
            refresh_token = data.get("refresh_token", "")
            redirect_url = data.get("url", "")
            if redirect_url:
                r2 = client.get(redirect_url, follow_redirects=True)
                cookies.update(dict(client.cookies))
            return {"cookies": cookies, "refresh_token": refresh_token}

        elif code == 86038:
            raise RuntimeError("QR code expired. Please try again.")
        elif code == 86090:
            console.print("  Scanned — waiting for confirmation on your phone...", end="\r")
        elif code == 86101:
            pass  # Waiting for scan
        else:
            console.print(f"  Status: {code}", end="\r")

        time.sleep(2)

    raise TimeoutError("Login timed out after 120 seconds. Please try again.")


def _bili_save_cookies(login_data: dict) -> None:
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(COOKIE_PATH, "w") as f:
        json.dump(login_data, f, indent=2)


def _bili_test_login(login_data: dict) -> list[dict]:
    """Fetch Bilibili favorites list to verify login. Returns folder list."""
    cookies = login_data.get("cookies", {})
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
        return data.get("data", {}).get("list", [])
    return []


def login_bilibili(force: bool = False) -> bool:
    """Interactive Bilibili QR login flow.

    Returns True on success, False on cancellation.
    Saves cookies to ~/.omnifeed/bilibili_cookies.json.
    On success, automatically mines favorites for profile interests.
    """
    console.print("\n[bold cyan]Bilibili 扫码登录[/bold cyan]\n")

    # Check existing login
    if COOKIE_PATH.exists() and not force:
        with open(COOKIE_PATH) as f:
            existing = json.load(f)
        mid = existing.get("cookies", {}).get("DedeUserID", "")
        if mid:
            console.print(f"  Already logged in (UID: {mid})")
            import click
            if not click.confirm("  Re-login?", default=False):
                console.print("  Keeping existing login.")
                return True

    try:
        url, key = _bili_generate_qr()
        console.print("  Scan this QR code with the Bilibili app:\n")
        _bili_show_qr(url)
        console.print("\n  Waiting for scan...")

        login_data = _bili_poll(key)
        _bili_save_cookies(login_data)

        cookies = login_data["cookies"]
        mid = cookies.get("DedeUserID", "?")
        sessdata = cookies.get("SESSDATA", "")
        console.print(f"\n  [green]Login successful[/green] (UID: {mid})")
        console.print(f"  SESSDATA: {sessdata[:20]}...")
        console.print(f"  Saved to: {COOKIE_PATH}")

        # Test and show favorites
        console.print("\n  Checking favorites...")
        folders = _bili_test_login(login_data)
        if folders:
            console.print(f"  Found {len(folders)} favorite folder(s):")
            for folder in folders[:5]:
                console.print(f"    - {folder['title']} ({folder['media_count']} videos)")

        return True

    except (RuntimeError, TimeoutError) as e:
        console.print(f"\n  [red]Login failed:[/red] {e}")
        return False
    except Exception as e:
        console.print(f"\n  [red]Unexpected error:[/red] {e}")
        return False


# ── GitHub ────────────────────────────────────────────────────────────────────

def login_github(token: Optional[str] = None) -> bool:
    """GitHub login via gh CLI or personal access token.

    Returns True on success, False on failure.
    After auth, fetches starred repos and reports detected interests.
    """
    console.print("\n[bold cyan]GitHub Login[/bold cyan]\n")

    # Try gh CLI first
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            console.print("  [green]gh CLI already authenticated[/green]")
            _gh_show_stars_summary()
            return True
        else:
            console.print("  gh CLI is not authenticated.")
    except FileNotFoundError:
        console.print("  gh CLI not found.")
        token = token or _prompt_gh_token()
        if token:
            return _login_github_with_token(token)
        return False
    except Exception as e:
        console.print(f"  [yellow]gh CLI check failed:[/yellow] {e}")

    # Offer to run gh auth login
    import click
    if click.confirm("  Run 'gh auth login' now?", default=True):
        try:
            subprocess.run(["gh", "auth", "login"], timeout=120)
            result = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                console.print("  [green]GitHub auth successful[/green]")
                _gh_show_stars_summary()
                return True
        except Exception as e:
            console.print(f"  [red]gh auth login failed:[/red] {e}")

    # Fall back to token
    if click.confirm("  Use a Personal Access Token instead?", default=False):
        token = _prompt_gh_token()
        if token:
            return _login_github_with_token(token)

    return False


def _prompt_gh_token() -> Optional[str]:
    """Prompt for a GitHub Personal Access Token."""
    import click
    console.print("  Create a token at: https://github.com/settings/tokens")
    console.print("  Required scopes: read:user, repo (for private repos)")
    token = click.prompt("  GitHub Personal Access Token", hide_input=True, default="")
    return token.strip() or None


def _login_github_with_token(token: str) -> bool:
    """Verify token and save to config."""
    try:
        r = httpx.get(
            "https://api.github.com/user",
            headers={"Authorization": f"token {token}", "User-Agent": "omnifeed"},
            timeout=10,
        )
        if r.status_code == 200:
            username = r.json().get("login", "?")
            console.print(f"  [green]Token valid[/green] (user: {username})")
            # Save token to config
            _save_github_token(token, username)
            _gh_show_stars_summary(token=token, username=username)
            return True
        else:
            console.print(f"  [red]Token invalid:[/red] HTTP {r.status_code}")
            return False
    except Exception as e:
        console.print(f"  [red]Token verification failed:[/red] {e}")
        return False


def _save_github_token(token: str, username: str) -> None:
    """Save GitHub token to ~/.omnifeed/github_token.json."""
    token_path = Path("~/.omnifeed/github_token.json").expanduser()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        json.dump({"token": token, "username": username}, f, indent=2)


def _gh_show_stars_summary(token: Optional[str] = None, username: Optional[str] = None) -> None:
    """Fetch and display a summary of GitHub stars by topic."""
    try:
        headers = {"User-Agent": "omnifeed"}
        if token:
            headers["Authorization"] = f"token {token}"

        # Get username if not provided
        if not username:
            r = httpx.get("https://api.github.com/user", headers=headers, timeout=10)
            if r.status_code == 200:
                username = r.json().get("login", "")
            else:
                return

        if not username:
            return

        # Fetch first page of stars
        r = httpx.get(
            f"https://api.github.com/users/{username}/starred",
            params={"per_page": 30, "page": 1},
            headers=headers, timeout=10,
        )
        if r.status_code != 200:
            return

        repos = r.json()
        from collections import Counter
        topics: Counter = Counter()
        for repo in repos:
            for t in repo.get("topics", []):
                topics[t] += 1

        if topics:
            console.print(f"\n  Top topics from {username}'s stars:")
            for t, count in topics.most_common(8):
                console.print(f"    - {t} ({count})")
    except Exception:
        pass


# ── LLM API Key Verification ──────────────────────────────────────────────────

def verify_api_key(provider: str, base_url: str, api_key: str) -> bool:
    """Test an LLM API key with a minimal request.

    Args:
        provider: "anthropic" or "openai" (or any openai-compatible)
        base_url:  API base URL (e.g. "https://api.anthropic.com")
        api_key:   The key to test

    Returns True if the key works, False otherwise.
    """
    try:
        if provider == "anthropic":
            url = base_url.rstrip("/") + "/v1/messages"
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            payload = {
                "model": "claude-haiku-4-20250514",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            r = httpx.post(url, headers=headers, json=payload, timeout=15)
            return r.status_code == 200

        else:
            # OpenAI-compatible
            url = base_url.rstrip("/") + "/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            }
            payload = {
                "model": "gpt-4o-mini",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "Hi"}],
            }
            r = httpx.post(url, headers=headers, json=payload, timeout=15)
            return r.status_code == 200

    except Exception:
        return False


# ── Auto Profile Builder ──────────────────────────────────────────────────────

def auto_build_profile(config: dict) -> dict:
    """Build interest profile from all available authenticated sources.

    config: dict with keys like 'github_user', 'ai_enabled', etc.
    Returns: the profile dict (also saved to disk).
    """
    from .profile import build_deep_profile
    github_user = config.get("github_user", "")
    console.print("\n  [dim]Building interest profile...[/dim]")
    profile = build_deep_profile(github_user=github_user, force=True)
    return profile
