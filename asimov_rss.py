#!/usr/bin/env python3
"""Build an RSS 2.0 feed for Asimov Press (https://press.asimov.com).

The site publishes no feed, so this scrapes the /articles archive page.
Usage:  python asimov_rss.py [output_path] [max_items]
Needs:  pip install requests beautifulsoup4
"""
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup

BASE = "https://press.asimov.com"
ARCHIVE = f"{BASE}/articles"
CATEGORIES = r"(Updates|Essay|Long Reads|Fiction|Data|Podcast|Interview)"
META_RE = re.compile(CATEGORIES + r"\s*·\s*([A-Z][a-z]+ \d{1,2}, \d{4})")
HEADERS = {"User-Agent": "Mozilla/5.0 (personal RSS feed builder)"}


def parse_date(text):
    return datetime.strptime(text, "%B %d, %Y").replace(hour=12, tzinfo=timezone.utc)


def article_meta(url):
    """Fallback: read title/description from the article page's meta tags."""
    try:
        soup = BeautifulSoup(requests.get(url, headers=HEADERS, timeout=20).text, "html.parser")
    except requests.RequestException:
        return None, None

    def meta(prop):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        return tag["content"].strip() if tag and tag.get("content") else None

    title = meta("og:title") or (soup.title.string if soup.title else None)
    if title:
        title = re.sub(r"\s*[—-]\s*Asimov Press$", "", title)
    return title, meta("og:description") or meta("description")


def scrape(max_items):
    html = requests.get(ARCHIVE, headers=HEADERS, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()

    for a in soup.find_all("a", href=True):
        href = a["href"].split("#")[0].split("?")[0]
        if not re.match(r"^(https://press\.asimov\.com)?/articles/[^/]+/?$", href):
            continue
        url = href if href.startswith("http") else BASE + href
        text = a.get_text(" ", strip=True)
        m = META_RE.search(text)
        if url in seen or not m:
            continue
        seen.add(url)
        category, date = m.group(1), parse_date(m.group(2))

        heading = a.find(["h1", "h2", "h3", "h4"])
        para = a.find("p")
        author_tag = a.find("strong")
        title = heading.get_text(" ", strip=True) if heading else None
        desc = para.get_text(" ", strip=True) if para else None
        author = author_tag.get_text(" ", strip=True) if author_tag else None

        if not title or not desc:
            meta_title, meta_desc = article_meta(url)
            title = title or meta_title or url.rsplit("/", 1)[-1]
            desc = desc or meta_desc or ""

        items.append(dict(url=url, title=title, desc=desc, author=author,
                          category=category, date=date))

    items.sort(key=lambda i: i["date"], reverse=True)
    return items[:max_items]


def build_rss(items):
    now = format_datetime(datetime.now(timezone.utc))
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">',
        "<channel>",
        "<title>Asimov Press</title>",
        f"<link>{BASE}/</link>",
        "<description>Deep writing on big ideas in biotechnology. "
        "(Unofficial feed generated from press.asimov.com/articles.)</description>",
        "<language>en-us</language>",
        f"<lastBuildDate>{now}</lastBuildDate>",
        f"<image><url>{BASE}/social/asimov-press-v1.png</url>"
        f"<title>Asimov Press</title><link>{BASE}/</link></image>",
    ]
    for i in items:
        out += [
            "<item>",
            f"<title>{escape(i['title'])}</title>",
            f"<link>{escape(i['url'])}</link>",
            f'<guid isPermaLink="true">{escape(i["url"])}</guid>',
            f"<pubDate>{format_datetime(i['date'])}</pubDate>",
            f"<category>{escape(i['category'])}</category>",
        ]
        if i.get("author"):
            out.append(f"<dc:creator>{escape(i['author'])}</dc:creator>")
        out += [f"<description>{escape(i['desc'])}</description>", "</item>"]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "feed.xml"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    items = scrape(limit)
    if not items:
        sys.exit("No articles found — the site layout may have changed.")
    with open(path, "w", encoding="utf-8") as f:
        f.write(build_rss(items))
    print(f"Wrote {len(items)} items to {path}")
