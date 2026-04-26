#!/usr/bin/env python3
"""Fetch Telegram chat IDs from recent bot updates."""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from runtime_env import apply_runtime_env
except ImportError:
    apply_runtime_env = None


def main() -> int:
    if apply_runtime_env is not None:
        try:
            apply_runtime_env(load_secrets=True)
        except Exception as exc:
            print(f"Warning: Failed to load runtime environment: {exc}", file=sys.stderr)

    token = os.environ.get("JOB_AGENT_TELEGRAM_BOT_TOKEN")
    if not token:
        print("JOB_AGENT_TELEGRAM_BOT_TOKEN not found in environment.", file=sys.stderr)
        print("Ensure it is exported in your shell or secrets.sh.", file=sys.stderr)
        return 1

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    request = Request(url, headers={"Accept": "application/json"})
    
    try:
        with urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except URLError as exc:
        print(f"Failed to fetch updates: {exc}", file=sys.stderr)
        return 1

    if not data.get("ok"):
        print(f"Telegram API error: {data.get('description')}", file=sys.stderr)
        return 1

    results = data.get("result", [])
    if not results:
        print("No recent updates found. Open your bot, press Start, send a short message such as \"hi\", then retry.")
        return 0

    seen_chats = {}
    for update in results:
        message = update.get("message") or update.get("channel_post") or update.get("my_chat_member", {}).get("chat")
        if not message:
            continue
        
        chat = message.get("chat") if "chat" in message else message
        chat_id = chat.get("id")
        chat_title = chat.get("title") or chat.get("username") or chat.get("first_name", "Unknown")
        chat_type = chat.get("type")
        
        seen_chats[chat_id] = {"title": chat_title, "type": chat_type}

    print("Recent Chat IDs:")
    for chat_id, info in seen_chats.items():
        print(f"- {chat_id} ({info['title']}, type: {info['type']})")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
