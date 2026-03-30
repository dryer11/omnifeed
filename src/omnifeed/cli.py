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
