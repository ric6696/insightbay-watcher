"""Notify a Slack/Discord webhook when a new InsightBay position matches a keyword."""

import json
import os
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_URL = "https://www.insightbay.co.kr"
LIST_URL = f"{BASE_URL}/v2/positions"
SEEN_FILE = Path(__file__).with_name("seen.json")
USER_AGENT = "Mozilla/5.0 (insightbay-watcher)"


class PositionParser(HTMLParser):
    """Collects {id, url, title, deadline, expired} from each `a.job-group` card."""

    def __init__(self):
        super().__init__()
        self.positions = []
        self._card = None
        self._in_h3 = False
        self._in_li = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        if tag == "a" and "job-group" in classes:
            match = re.search(r"/view/(\d+)/", attrs.get("href", ""))
            if match:
                self._card = {
                    "id": int(match.group(1)),
                    "url": BASE_URL + attrs["href"],
                    "title": "",
                    "meta": [],
                    "expired": False,
                }
        elif self._card is None:
            return
        elif tag == "div" and "expired" in classes:
            self._card["expired"] = True
        elif tag == "h3":
            self._in_h3 = True
        elif tag == "li":
            self._in_li = True

    def handle_endtag(self, tag):
        if self._card is None:
            return
        if tag == "h3":
            self._in_h3 = False
        elif tag == "li":
            self._in_li = False
        elif tag == "a":
            card = self._card
            card["title"] = " ".join(card["title"].split())
            # meta = [location, deadline, views]
            card["deadline"] = card["meta"][1] if len(card["meta"]) > 1 else ""
            del card["meta"]
            self.positions.append(card)
            self._card = None

    def handle_data(self, data):
        if self._card is None:
            return
        if self._in_h3:
            self._card["title"] += data
        elif self._in_li and data.strip():
            self._card["meta"].append(data.strip())


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def parse_positions(html):
    parser = PositionParser()
    parser.feed(html)
    return parser.positions


def notify(webhook_url, position):
    text = (
        f"🔔 새 공고: {position['title']}\n"
        f"마감일: {position['deadline'] or '-'}\n"
        f"{position['url']}"
    )
    key = "content" if "discord.com" in webhook_url else "text"
    req = urllib.request.Request(
        webhook_url,
        data=json.dumps({key: text}).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
    )
    urllib.request.urlopen(req, timeout=15).close()


def open_draft_issue(position):
    """Open a `draft-request` issue; a Claude routine listens for it and writes the application draft."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/issues",
        data=json.dumps({
            "title": f"[초안] {position['title']}",
            "body": f"공고: {position['url']}\n마감일: {position['deadline'] or '-'}",
            "labels": ["draft-request"],
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    urllib.request.urlopen(req, timeout=15).close()


def main():
    keywords = [k.strip().lower() for k in os.environ.get("KEYWORDS", "").split(",") if k.strip()]
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    draft_issues = os.environ.get("DRAFT_ISSUES", "").lower() == "true"
    if not keywords or not webhook_url:
        sys.exit("KEYWORDS and WEBHOOK_URL environment variables are required")

    positions = parse_positions(fetch(LIST_URL))
    if not positions:
        sys.exit("No positions parsed — the page structure may have changed")

    if not SEEN_FILE.exists():
        # First run: record what is already listed instead of alerting on old posts.
        SEEN_FILE.write_text(json.dumps(sorted(p["id"] for p in positions)) + "\n")
        print(f"Initialized {SEEN_FILE.name} with {len(positions)} positions")
        return

    seen = set(json.loads(SEEN_FILE.read_text()))
    sent = 0
    try:
        for position in positions:
            if position["id"] in seen:
                continue
            if any(k in position["title"].lower() for k in keywords):
                notify(webhook_url, position)
                if draft_issues:
                    open_draft_issue(position)
                sent += 1
                print(f"Notified: {position['id']} {position['title']}")
            seen.add(position["id"])
    finally:
        # Persist progress even if a later webhook call fails, so sent alerts are not repeated.
        SEEN_FILE.write_text(json.dumps(sorted(seen)) + "\n")
    print(f"Checked {len(positions)} positions, sent {sent} notifications")


if __name__ == "__main__":
    main()
