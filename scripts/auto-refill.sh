#!/bin/bash
# OmniFeed auto-refill — runs every 2h to keep pool fresh
# Logs to ~/.omnifeed/logs/

set -e
export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.npm-global/bin:$PATH"
export PYTHONPATH="$HOME/.openclaw/workspace/projects/omnifeed/src"

LOG_DIR="$HOME/.omnifeed/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refill-$(date +%Y%m%d).log"

echo "=== $(date) ===" >> "$LOG"

# Ensure XHS MCP is running
bash "$HOME/.agent-reach/tools/ensure-xhs-mcp.sh" >> "$LOG" 2>&1 || true

# Run fetch
cd "$HOME/.openclaw/workspace/projects/omnifeed"
python3 -m omnifeed.cli fetch >> "$LOG" 2>&1

# Cleanup old logs (keep 7 days)
find "$LOG_DIR" -name "refill-*.log" -mtime +7 -delete 2>/dev/null || true

echo "=== done ===" >> "$LOG"
