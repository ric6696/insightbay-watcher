"""Notify a Slack/Discord webhook when a new InsightBay position matches a keyword."""

import html
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


def posting_text(html_text):
    """Plain text of a posting's `div.job-detail` block (duties, requirements, how to apply, company info)."""
    start = html_text.index('<div class="job-detail"')
    end = html_text.rindex("<div", start, html_text.index('class="job-class"'))
    block = re.sub(r"(?s)<(script|style)\b.*?</\1>", "", html_text[start:end])
    block = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d)>", "\n", block)
    block = html.unescape(re.sub(r"<[^>]+>", " ", block))
    return "\n".join(" ".join(line.split()) for line in block.splitlines() if line.strip())


def open_draft_issue(position):
    """Open a `draft-request` issue; a Claude routine listens for it and writes the application draft.

    The posting text goes into the issue because the routine's sandbox cannot reach InsightBay.
    """
    text = posting_text(fetch(position["url"]))
    req = urllib.request.Request(
        f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/issues",
        data=json.dumps({
            "title": f"[초안] {position['title']}",
            "body": (
                f"공고: {position['url']}\n마감일: {position['deadline'] or '-'}\n\n"
                f"## 공고 본문\n```\n{text}\n```"
            ),
            "labels": ["draft-request"],
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
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
    if draft_issues and not (os.environ.get("GITHUB_TOKEN") and os.environ.get("GITHUB_REPOSITORY")):
        sys.exit("DRAFT_ISSUES requires GITHUB_TOKEN and GITHUB_REPOSITORY environment variables")

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
    issue_errors = []
    try:
        for position in positions:
            if position["id"] in seen:
                continue
            if any(k in position["title"].lower() for k in keywords):
                notify(webhook_url, position)
                if draft_issues:
                    # The alert already went out: a failed issue must not block marking it seen,
                    # or every later run would re-send the same webhook alert.
                    try:
                        open_draft_issue(position)
                    except Exception as e:
                        issue_errors.append(f"{position['id']}: {e}")
                sent += 1
                print(f"Notified: {position['id']} {position['title']}")
            seen.add(position["id"])
    finally:
        # Persist progress even if a later webhook call fails, so sent alerts are not repeated.
        SEEN_FILE.write_text(json.dumps(sorted(seen)) + "\n")
    print(f"Checked {len(positions)} positions, sent {sent} notifications")
    if issue_errors:
        sys.exit("Failed to open draft issues:\n" + "\n".join(issue_errors))


if __name__ == "__main__":
    main()
