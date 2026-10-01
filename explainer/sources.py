"""Source gathering: local topic-pack docs, user URLs, or a Wikipedia fallback."""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from .util import log

UA = "explainer-pipeline/0.1 (offline-first educational video generator)"


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "footer", "header", "noscript", "svg", "form"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in {"p", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    text = "".join(p.parts)
    text = re.sub(r"\[\d+\]", "", text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if len(ln) > 40)


def _get(url: str, timeout: int = 20) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_url(url: str) -> str:
    body = _get(url)
    return html_to_text(body) if "<html" in body[:2000].lower() or "<p" in body.lower() else body


def wikipedia_extract(topic: str) -> tuple[str, str] | None:
    """Search Wikipedia for the topic and return (page_url, plain-text extract)."""
    q = re.sub(r"^(how|what|why)\s+(does|do|is|are)?\s*(an?|the)?\s*", "", topic.strip(), flags=re.I)
    q = re.sub(r"\s+(works?|work)$", "", q, flags=re.I) or topic
    api = "https://en.wikipedia.org/w/api.php"
    try:
        s = json.loads(_get(f"{api}?action=query&list=search&format=json&srlimit=1&srsearch="
                            + urllib.parse.quote(q)))
        hits = s["query"]["search"]
        if not hits:
            return None
        title = hits[0]["title"]
        e = json.loads(_get(f"{api}?action=query&prop=extracts&explaintext=1&format=json&redirects=1&titles="
                            + urllib.parse.quote(title)))
        page = next(iter(e["query"]["pages"].values()))
        text = page.get("extract", "")
        text = re.split(r"\n==\s*(See also|References|External links|Notes|Further reading)\s*==", text)[0]
        return f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}", text
    except Exception as exc:  # network is optional
        log(f"    wikipedia fetch failed: {exc}")
        return None


def gather(topic: str, topic_dir: Path, urls: list[str], allow_wikipedia: bool) -> list[dict]:
    """Returns [{name, origin, text}] — origin is a URL or a repo-relative file name."""
    docs = local_docs(topic_dir, urls)
    if not docs and allow_wikipedia:
        wp = wikipedia_extract(topic)
        if wp:
            docs.append({"name": "wikipedia", "origin": wp[0], "text": wp[1]})
    return docs


def local_docs(topic_dir: Path, urls: list[str]) -> list[dict]:
    """Topic-pack files plus user-supplied URLs (never Wikipedia)."""
    docs = []
    src_dir = topic_dir / "sources"
    if src_dir.is_dir():
        for f in sorted(src_dir.iterdir()):
            if f.suffix in {".md", ".txt"}:
                docs.append({"name": f.stem, "origin": f"topics/{topic_dir.name}/sources/{f.name}",
                             "text": f.read_text()})
    url_file = topic_dir / "sources.txt"
    if url_file.exists():
        urls = urls + [u.strip() for u in url_file.read_text().splitlines()
                       if u.strip() and not u.startswith("#")]
    for u in urls:
        try:
            log(f"    fetching {u}")
            docs.append({"name": urllib.parse.urlparse(u).netloc, "origin": u, "text": fetch_url(u)})
        except Exception as exc:
            log(f"    could not fetch {u}: {exc}")
    return docs
