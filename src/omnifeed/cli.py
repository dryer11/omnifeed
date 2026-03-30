"""OmniFeed CLI."""

from __future__ import annotations
import click
from pathlib import Path
from rich.console import Console

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """🌊 OmniFeed — Cross-platform personalized content aggregator."""
    pass


@main.command()
@click.option("--path", "-p", default=None, help="Config file path")
def init(path):
    """Initialize config file."""
    from .config import init_config
    config_path = init_config(path)
    console.print(f"\nConfig created: [bold]{config_path}[/bold]")
    console.print("Edit it to set your interests, then run: [bold]omnifeed fetch[/bold]\n")


@main.command()
def setup():
    """Interactive setup wizard — configure OmniFeed from scratch."""
    import webbrowser
    from .config import DEFAULT_CONFIG_DIR, DEFAULT_CONFIG_FILE

    console.print("\n[bold cyan]🌊 Welcome to OmniFeed![/bold cyan]\n")
    console.print("This wizard will help you get set up in just a few steps.\n")

    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: About You ──────────────────────────────────────────────────
    console.print("[bold]Step 1/4 — About You[/bold]")

    name = click.prompt("  Your name", default="", show_default=False)
    location = click.prompt("  Location (for local content)", default="", show_default=False)
    identity = click.prompt(
        "  Identity (e.g. \"AI researcher\", \"student\")", default="", show_default=False
    )
    github_user = click.prompt(
        "  GitHub username (optional, for interest mining)", default="", show_default=False
    )

    interests_raw = click.prompt(
        "  Your interests (comma-separated, e.g. AI,Python,research)",
        default="AI,Technology",
    )
    interests_list = [t.strip() for t in interests_raw.split(",") if t.strip()]

    console.print()

    # ── Step 2: Platform Login ─────────────────────────────────────────────
    console.print("[bold]Step 2/4 — Platform Login[/bold]")
    console.print()
    console.print("  Platforms available:")
    console.print("    [1] Bilibili — 扫码登录 (recommended, mines favorites for interests)")
    console.print("    [2] GitHub — uses gh CLI or token")
    console.print("    [3] Reddit — no login needed")
    console.print("    [4] V2EX — no login needed")
    console.print("    [5] 小红书 — requires MCP server (advanced)")
    console.print("    [6] Done")
    console.print()

    logged_in_platforms: list[str] = []
    bili_logged_in = False
    gh_logged_in = False

    while True:
        choice = click.prompt(
            "  Login to platform (number, or 6 to skip)", default="6"
        ).strip()

        if choice == "1":
            from .login import login_bilibili
            if login_bilibili():
                bili_logged_in = True
                logged_in_platforms.append("bilibili")
        elif choice == "2":
            from .login import login_github
            if login_github():
                gh_logged_in = True
                logged_in_platforms.append("github")
        elif choice in ("3", "4"):
            platform = "reddit" if choice == "3" else "v2ex"
            console.print(f"  {platform} will be enabled (no login needed).")
            logged_in_platforms.append(platform)
        elif choice == "5":
            console.print("  小红书 requires a local MCP server.")
            console.print("  See: scripts/xhs-refresh-login.sh for setup instructions.")
        elif choice == "6":
            break
        else:
            console.print("  Invalid choice. Enter 1-6.")

        console.print()

    # ── Step 3: AI Engine ──────────────────────────────────────────────────
    console.print("[bold]Step 3/4 — AI Engine[/bold]")
    console.print()
    console.print("  OmniFeed uses an LLM for smarter content discovery.")
    console.print()
    console.print("    [1] Anthropic (Claude) — recommended")
    console.print("    [2] OpenAI compatible")
    console.print("    [3] Skip (rule-based only)")
    console.print()

    ai_provider = ""
    ai_base_url = ""
    ai_api_key = ""
    ai_model = ""
    ai_enabled = False

    ai_choice = click.prompt("  Provider", default="3").strip()

    if ai_choice in ("1", "2"):
        if ai_choice == "1":
            ai_provider = "anthropic"
            ai_base_url = "https://api.anthropic.com"
            ai_model = "claude-haiku-4-20250514"
            console.print("  Using Anthropic Claude.")
        else:
            ai_provider = "openai"
            ai_base_url = click.prompt(
                "  Base URL", default="https://api.openai.com"
            ).strip()
            ai_model = click.prompt("  Model name", default="gpt-4o-mini").strip()

        ai_api_key = click.prompt("  API Key", hide_input=True, default="").strip()

        if ai_api_key:
            console.print("  Verifying API key...", end="")
            from .login import verify_api_key
            ok = verify_api_key(ai_provider, ai_base_url, ai_api_key)
            if ok:
                console.print(" [green]OK[/green]")
                ai_enabled = True
            else:
                console.print(" [red]FAILED[/red]")
                console.print("  Continuing without AI (you can add it later in config.yaml).")
        else:
            console.print("  No key provided — skipping AI.")

    console.print()

    # ── Step 4: Generate Profile ───────────────────────────────────────────
    console.print("[bold]Step 4/4 — Generating your profile...[/bold]")
    console.print()

    # Build channel config
    default_enabled = {"v2ex", "reddit", "rss"}
    if bili_logged_in:
        default_enabled.add("bilibili")
    if gh_logged_in:
        default_enabled.add("github")
    # Always enable weibo for trending
    default_enabled.add("weibo")

    # Build interests YAML block
    interest_lines = ""
    for idx, topic in enumerate(interests_list):
        weight = 5 if idx == 0 else 3
        interest_lines += f'    - topic: "{topic}"\n      weight: {weight}\n'
    if not interest_lines:
        interest_lines = '    - topic: "Technology"\n      weight: 3\n'

    # Build ai YAML block
    if ai_enabled and ai_api_key:
        ai_block = (
            f"ai:\n"
            f"  enabled: true\n"
            f"  model: \"{ai_model}\"\n"
            f"  base_url: \"{ai_base_url}\"\n"
            f"  api_key: \"{ai_api_key}\"\n"
            f"  features: [query_gen, categorize, summarize, recommend_reason]\n"
            f"  batch_size: 15\n"
        )
    else:
        ai_block = (
            "ai:\n"
            "  enabled: false\n"
            "  # To enable: set enabled: true, add model and api_key\n"
        )

    # Build channels YAML
    all_channels = ["weibo", "v2ex", "github", "reddit", "rss", "bilibili", "xhs"]
    channel_lines = ""
    for ch in all_channels:
        enabled_flag = "true" if ch in default_enabled else "false"
        if ch == "v2ex":
            channel_lines += f"  {ch}:\n    enabled: {enabled_flag}\n    nodes: [python, ai, jobs]\n"
        elif ch == "reddit":
            channel_lines += (
                f"  {ch}:\n    enabled: {enabled_flag}\n"
                f"    subreddits: [MachineLearning, LocalLLaMA]\n"
            )
        else:
            channel_lines += f"  {ch}:\n    enabled: {enabled_flag}\n"

    github_user_line = f'  github_user: "{github_user}"' if github_user else ""

    config_yaml = (
        "# OmniFeed Configuration\n"
        "# Generated by omnifeed setup\n\n"
        "profile:\n"
        f'  name: "{name}"\n'
        f'  location: "{location}"\n'
        f'  identity: "{identity}"\n'
        + (f"{github_user_line}\n" if github_user_line else "")
        + "\n  interests:\n"
        + interest_lines
        + "\n  follows: []\n"
        + "  feeds: []\n\n"
        + "channels:\n"
        + channel_lines
        + "\noutput:\n"
        + "  html: true\n"
        + "  json: true\n"
        + "  daily_digest: false\n"
        + '  dir: "~/.omnifeed/output"\n\n'
        + ai_block
        + "\nschedule:\n"
        + '  fetch_interval: "4h"\n'
        + '  digest_time: "08:00"\n'
        + '  timezone: "Asia/Shanghai"\n'
    )

    DEFAULT_CONFIG_FILE.write_text(config_yaml)
    console.print(f"  Config written to: {DEFAULT_CONFIG_FILE}")

    # Auto-build profile if we have data sources
    if github_user or bili_logged_in:
        console.print("  Building interest profile from your data...")
        try:
            from .login import auto_build_profile
            profile = auto_build_profile({"github_user": github_user})
            top = sorted(profile.get("topics", {}).items(), key=lambda x: x[1], reverse=True)[:5]
            if top:
                console.print("  Top interests detected:")
                for topic, weight in top:
                    bar = "█" * min(8, int(weight))
                    console.print(f"    {topic:25s} {bar}")
        except Exception as e:
            console.print(f"  [yellow]Profile build skipped:[/yellow] {e}")

    # Offer first fetch
    console.print()
    if click.confirm("  Run your first fetch now?", default=True):
        from .config import load_config
        from .engine import fetch as run_fetch
        from .renderer import render_html, render_json
        import time as _time

        console.print()
        cfg = load_config()
        result = run_fetch(cfg)

        output_dir = Path(cfg.output.dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)

        html_path = None
        if cfg.output.html:
            html_path = render_html(result, str(output_dir / "index.html"))
            console.print(f"  HTML: [link=file://{html_path}]{html_path}[/link]")

        if cfg.output.json:
            json_path = render_json(result, str(output_dir / "feed.json"))
            console.print(f"  JSON: {json_path}")

        # Auto-open browser
        if html_path and click.confirm("\n  Open in browser?", default=True):
            webbrowser.open(f"file://{html_path}")

    console.print()
    console.print("[bold green]Setup complete![/bold green]")
    console.print("Run [bold]omnifeed fetch[/bold] any time to refresh your feed.")
    console.print("Run [bold]omnifeed serve[/bold] to preview in browser.\n")


@main.group()
def login():
    """Login to content platforms."""
    pass


@login.command(name="bilibili")
@click.option("--force", is_flag=True, help="Re-login even if already authenticated")
def login_bilibili_cmd(force):
    """Login to Bilibili via QR code scan."""
    from .login import login_bilibili, auto_build_profile
    success = login_bilibili(force=force)
    if success:
        if click.confirm("\nAnalyze Bilibili favorites and update profile?", default=True):
            try:
                profile = auto_build_profile({})
                top = sorted(profile.get("topics", {}).items(), key=lambda x: x[1], reverse=True)[:8]
                console.print("\nDiscovered interests:")
                for topic, weight in top:
                    bar = "█" * min(10, int(weight))
                    console.print(f"  {topic:25s} {bar} ({weight})")
            except Exception as e:
                console.print(f"[yellow]Profile build failed:[/yellow] {e}")


@login.command(name="github")
@click.option("--token", "-t", default=None, help="Personal access token")
def login_github_cmd(token):
    """Login to GitHub via gh CLI or personal access token."""
    from .login import login_github, auto_build_profile
    success = login_github(token=token)
    if success:
        if click.confirm("\nFetch GitHub stars and update profile?", default=True):
            try:
                # Try to get username from gh CLI or token
                import subprocess, httpx
                username = ""
                try:
                    result = subprocess.run(
                        ["gh", "api", "user", "--jq", ".login"],
                        capture_output=True, text=True, timeout=10,
                    )
                    if result.returncode == 0:
                        username = result.stdout.strip()
                except Exception:
                    pass

                profile = auto_build_profile({"github_user": username})
                top = sorted(profile.get("topics", {}).items(), key=lambda x: x[1], reverse=True)[:8]
                console.print("\nDiscovered interests:")
                for topic, weight in top:
                    bar = "█" * min(10, int(weight))
                    console.print(f"  {topic:25s} {bar} ({weight})")
            except Exception as e:
                console.print(f"[yellow]Profile build failed:[/yellow] {e}")


@main.command()
@click.option("--github", "-g", default="dryer11", help="GitHub username for stars")
@click.option("--force", is_flag=True, help="Force re-initialize")
def profile(github, force):
    """Initialize interest profile from platform data (GitHub stars, etc)."""
    from .profile import build_deep_profile
    p = build_deep_profile(github_user=github, force=force)
    console.print(f"\nProfile initialized from: {', '.join(p.get('sources_used', []))}")
    console.print(f"Topics: {len(p.get('topics', {}))} detected")
    # Show top topics
    sorted_t = sorted(p.get("topics", {}).items(), key=lambda x: x[1], reverse=True)
    for t, w in sorted_t[:10]:
        bar = "█" * min(10, int(w))
        console.print(f"  {t:25s} {bar} ({w})")
    console.print(f"\nKeywords: {len(p.get('keywords', []))}")
    console.print(f"Languages: {p.get('languages', {})}")
    console.print(f"Saved to: ~/.omnifeed/profile.json\n")


@main.command()
@click.option("--config", "-c", default=None, help="Config file path")
def doctor(config):
    """Check channel availability."""
    from .config import load_config
    from .engine import doctor as run_doctor
    cfg = load_config(config)
    run_doctor(cfg)


@main.command()
@click.option("--config", "-c", default=None, help="Config file path")
@click.option("--channel", "-ch", multiple=True, help="Only fetch specific channel(s)")
@click.option("--dry-run", is_flag=True, help="Show query plan without fetching")
def fetch(config, channel, dry_run):
    """Fetch content from all platforms."""
    from .config import load_config
    from .engine import fetch as run_fetch
    from .renderer import render_html, render_json

    cfg = load_config(config)

    if not cfg.enabled_channels() and not channel:
        console.print("[yellow]No channels enabled. Run [bold]omnifeed init[/bold] first.[/yellow]")
        return

    channels = list(channel) if channel else None
    result = run_fetch(cfg, channels=channels, dry_run=dry_run)

    if dry_run:
        return

    # Output
    output_dir = Path(cfg.output.dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    if cfg.output.html:
        html_path = render_html(result, str(output_dir / "index.html"))
        console.print(f"  📄 HTML: [link=file://{html_path}]{html_path}[/link]")

    if cfg.output.json:
        json_path = render_json(result, str(output_dir / "feed.json"))
        console.print(f"  📋 JSON: {json_path}")

    if cfg.output.daily_digest:
        from .renderer import render_digest
        digest = render_digest(result)
        digest_path = output_dir / "digest.md"
        digest_path.write_text(digest, encoding="utf-8")
        console.print(f"  📰 Digest: {digest_path}")


@main.command()
@click.option("--config", "-c", default=None, help="Config file path")
@click.option("--port", "-p", default=8080, help="Port number")
def serve(config, port):
    """Preview feed locally."""
    from .config import load_config
    import http.server
    import functools

    cfg = load_config(config)
    output_dir = Path(cfg.output.dir).expanduser()

    if not (output_dir / "index.html").exists():
        console.print("[yellow]No output found. Run [bold]omnifeed fetch[/bold] first.[/yellow]")
        return

    console.print(f"\n🌐 Serving at [bold]http://localhost:{port}[/bold]  (Ctrl+C to stop)\n")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(output_dir))
    server = http.server.HTTPServer(("", port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n👋 Stopped.")


@main.command()
@click.option("--config", "-c", default=None, help="Config file path")
def build(config):
    """Rebuild HTML from cached feed data."""
    from .config import load_config
    from .renderer import render_html, render_json, render_digest
    from .models import FeedResult
    import json

    cfg = load_config(config)
    output_dir = Path(cfg.output.dir).expanduser()
    json_path = output_dir / "feed.json"

    if not json_path.exists():
        console.print("[yellow]No feed data found. Run [bold]omnifeed fetch[/bold] first.[/yellow]")
        return

    with open(json_path) as f:
        data = json.load(f)

    console.print(f"Loaded {data.get('stats', {}).get('final_items', '?')} items from cache")

    from .models import FeedItem, Engagement
    items = []
    for d in data.get("items", []):
        eng = d.get("engagement", {})
        item = FeedItem(
            id=d["id"], platform=d["platform"],
            title=d.get("title", ""), content=d.get("content", ""),
            author=d.get("author", ""), cover=d.get("cover", ""),
            url=d.get("url", ""), timestamp=d.get("timestamp", 0),
            engagement=Engagement(**eng) if isinstance(eng, dict) else Engagement(),
            category=d.get("category", ""),
            recommend_reason=d.get("recommend_reason", ""),
            tags=d.get("tags", []),
        )
        items.append(item)

    result = FeedResult(
        generated_at=data.get("generated_at", ""),
        profile_name=data.get("profile", ""),
        stats=data.get("stats", {}),
        items=items,
    )

    html_path = render_html(result, str(output_dir / "index.html"))
    console.print(f"  HTML: {html_path}")

    if cfg.output.daily_digest:
        digest = render_digest(result)
        digest_path = output_dir / "digest.md"
        digest_path.write_text(digest, encoding="utf-8")
        console.print(f"  Digest: {digest_path}")


@main.command()
def pool():
    """Show content pool status."""
    from .pool import pool_stats
    stats = pool_stats()
    console.print(f"\nContent Pool")
    console.print(f"  Total:    {stats['total']} items")
    console.print(f"  Fresh:    {stats['fresh']} (< 24h)")
    console.print(f"  Stale:    {stats['stale']}")
    console.print(f"  Seen:     {stats['seen']}")
    console.print(f"  Unseen:   {stats['unseen']}")
    console.print(f"  Refreshes available: {stats['refreshes_available']}")
    console.print(f"  Pool file: {stats['pool_file']}\n")


@main.command()
@click.option("--config", "-c", default=None, help="Config file path")
@click.option("--count", "-n", default=50, help="Items per page")
def refresh(config, count):
    """Draw fresh unseen items from pool and rebuild HTML."""
    from .config import load_config
    from .pool import pool_draw, pool_stats
    from .renderer import render_html, render_digest
    from .models import FeedResult
    from datetime import datetime, timezone, timedelta
    import time

    cfg = load_config(config)
    stats = pool_stats()

    if stats["unseen"] < 10:
        console.print(f"[yellow]Only {stats['unseen']} unseen items in pool. Run [bold]omnifeed fetch[/bold] to refill.[/yellow]")
        if stats["unseen"] == 0:
            return

    t0 = time.time()
    items = pool_draw(count=count)
    draw_ms = (time.time() - t0) * 1000

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)

    result = FeedResult(
        generated_at=now.isoformat(),
        profile_name=cfg.profile.name,
        stats={
            "platforms": len(set(it.platform for it in items)),
            "raw_items": len(items),
            "final_items": len(items),
            "from_pool": True,
        },
        items=items,
    )

    output_dir = Path(cfg.output.dir).expanduser()
    html_path = render_html(result, str(output_dir / "index.html"))

    new_stats = pool_stats()
    console.print(f"\n  Refreshed: {len(items)} items in {draw_ms:.0f}ms")
    console.print(f"  Remaining: {new_stats['unseen']} unseen in pool")
    console.print(f"  HTML: {html_path}\n")


if __name__ == "__main__":
    main()
