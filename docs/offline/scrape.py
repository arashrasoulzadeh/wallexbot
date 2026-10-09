"""Mirror developers.wallex.ir docs to Markdown + Swagger JSON (stdlib only).

Usage: python3 scrape.py
Output: pages/<slug>.md, swagger/*.json, INDEX.md (next to this script)
"""
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE = "https://developers.wallex.ir"
OUT = Path(__file__).parent
SEEDS = ["/docs", "/docs/spot-intro", "/docs/basic-services", "/docs/socket-intro",
         "/docs/margin-intro", "/docs/trade-credit-intro", "/docs/otc-intro"]
SKIP_CLASS = ("pagination-nav", "theme-doc-footer", "hash-link", "theme-doc-breadcrumbs",
              "theme-doc-toc-mobile", "clean-btn", "tocCollapsible")
VOID = {"br", "hr", "img", "input", "meta", "link"}


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


class ToMd(HTMLParser):
    """Convert the <article> subtree to Markdown."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack = [], []  # stack of (tag, skip)
        self.in_article = 0
        self.skip = 0
        self.pre = False
        self.href = []
        self.list = []  # ("ul"|"ol", counter)
        self.table = None  # rows
        self.row = None
        self.cell = None
        self.links = []

    def close_cell(self):
        if self.cell is not None:
            if self.row is not None:
                self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip().replace("|", "\\|"))
            self.cell = None

    def close_row(self):
        self.close_cell()
        if self.row is not None:
            if self.table is not None:
                self.table.append(self.row)
            self.row = None

    def w(self, s):
        if self.cell is not None:
            self.cell.append(s)
        else:
            self.out.append(s)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in VOID:
            if self.in_article and not self.skip:
                if tag == "br":
                    self.w("  \n" if self.cell is None else " ")
                elif tag == "hr":
                    self.w("\n\n---\n\n")
            return
        skip = tag in ("button", "svg", "script", "style", "nav") or any(c in cls for c in SKIP_CLASS)
        if tag == "article" and not self.in_article:
            self.in_article = 1
            self.stack.append((tag, False))
            return
        self.stack.append((tag, skip))
        if not self.in_article:
            return
        if skip:
            self.skip += 1
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.w("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self.w("\n\n")
        elif tag == "pre":
            self.pre = True
            self.w("\n\n```\n")
        elif tag == "code" and not self.pre:
            self.w("`")
        elif tag in ("strong", "b"):
            self.w("**")
        elif tag in ("em", "i"):
            self.w("*")
        elif tag == "a":
            self.href.append(a.get("href", ""))
            self.w("[")
        elif tag in ("ul", "ol"):
            self.list.append([tag, 0])
            self.w("\n")
        elif tag == "li":
            ind = "  " * (len(self.list) - 1)
            if self.list and self.list[-1][0] == "ol":
                self.list[-1][1] += 1
                self.w(f"\n{ind}{self.list[-1][1]}. ")
            else:
                self.w(f"\n{ind}- ")
        elif tag == "table":
            self.table = []
        elif tag in ("thead", "tbody"):
            self.close_row()
        elif tag == "tr":
            self.close_row()
            self.row = []
        elif tag in ("td", "th"):
            self.close_cell()
            self.cell = []
        elif tag == "blockquote":
            self.w("\n\n> ")
        elif tag == "div" and "admonition" in cls:
            self.w("\n\n> ")

    def handle_endtag(self, tag):
        if tag in VOID or not self.stack:
            return
        # pop to matching tag
        while self.stack and self.stack[-1][0] != tag:
            self.stack.pop()
        if not self.stack:
            return
        _, skip = self.stack.pop()
        if tag == "article" and self.in_article and not any(t == "article" for t, _ in self.stack):
            self.in_article = 0
            return
        if not self.in_article:
            return
        if skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.w("\n")
        elif tag == "pre":
            self.pre = False
            self.w("\n```\n")
        elif tag == "code" and not self.pre:
            self.w("`")
        elif tag in ("strong", "b"):
            self.w("**")
        elif tag in ("em", "i"):
            self.w("*")
        elif tag == "a":
            h = self.href.pop() if self.href else ""
            self.w(f"]({h})")
        elif tag in ("ul", "ol"):
            if self.list:
                self.list.pop()
            self.w("\n")
        elif tag in ("td", "th"):
            self.close_cell()
        elif tag == "tr":
            self.close_row()
        elif tag == "table":
            self.close_row()
            t, self.table = self.table or [], None
            if t:
                n = max(len(r) for r in t)
                rows = [r + [""] * (n - len(r)) for r in t]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * n]
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                self.w("\n\n" + "\n".join(lines) + "\n\n")

    def handle_data(self, data):
        if not self.in_article or self.skip:
            return
        if self.pre:
            self.w(data)
        else:
            data = data.replace("​", "")
            if data.strip() or (self.out and not self.out[-1].endswith("\n")):
                self.w(re.sub(r"\s+", " ", data))

    def md(self):
        s = "".join(self.out)
        s = re.sub(r"[ \t]+\n", "\n", s)
        return re.sub(r"\n{3,}", "\n\n", s).strip()


def slug(p):
    s = p.strip("/")
    s = s[5:] if s.startswith("docs/") else s
    return s.replace("/", "__") or "index"


def main():
    (OUT / "pages").mkdir(exist_ok=True)
    (OUT / "swagger").mkdir(exist_ok=True)
    queue, seen, index, swaggers = list(SEEDS), set(), [], set()
    while queue:
        p = queue.pop(0).split("#")[0].rstrip("/") or "/docs"
        if p in seen:
            continue
        seen.add(p)
        try:
            html = get(p)
        except Exception as e:
            print("FAIL", p, e)
            continue
        conv = ToMd()
        conv.feed(html)
        for h in conv.links:
            h = h.split("#")[0].rstrip("/")
            if h.startswith("/docs") and h not in seen:
                queue.append(h)
        swaggers.update(re.findall(r"/assets/files/[^\"'\s]+\.json", html))
        body = conv.md()
        if not body:
            print("EMPTY", p)
            continue
        m = re.match(r"#\s+(.+)", body)
        title = m.group(1) if m else p
        name = slug(p)
        (OUT / "pages" / f"{name}.md").write_text(
            f"<!-- source: {BASE}{p} -->\n\n{body}\n", encoding="utf-8")
        index.append((name, title, p))
        print("ok", p)
        time.sleep(0.1)
    for s in sorted(swaggers):
        req = urllib.request.Request(BASE + s, headers={"User-Agent": "Mozilla/5.0"})
        (OUT / "swagger" / Path(s).name).write_bytes(urllib.request.urlopen(req, timeout=30).read())
        print("swagger", s)
    lines = ["# Wallex docs offline mirror", "",
             f"Source: {BASE}/docs. {len(index)} pages. Regenerate with `python3 scrape.py`.", "",
             "## Swagger (machine-readable, authoritative)", ""]
    lines += [f"- [swagger/{f.name}](swagger/{f.name})" for f in sorted((OUT / "swagger").glob("*.json"))]
    lines += ["", "## Pages", ""]
    lines += [f"- [{t}](pages/{n}.md) (`{p}`)" for n, t, p in sorted(index, key=lambda x: x[2])]
    (OUT / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
