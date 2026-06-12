#!/usr/bin/env python3
"""
build_genome_report.py
Render output/health_summary.md -> output/specialist/genome_report.html,
themed to match the prefrontal-cortex dashboard (health.jlgao.net): the dark
"lab" palette, Space Grotesk / Space Mono, cyan accent, green=reassuring.
Stdlib only.
"""
import html
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MD_PATH = REPO_ROOT / "output" / "health_summary.md"
OUT_DIR = REPO_ROOT / "output" / "specialist"
OUT_PATH = OUT_DIR / "genome_report.html"

NUL = "\x00"


def escape(t: str) -> str:
    return html.escape(t, quote=False)


def slugify(t: str) -> str:
    s = re.sub(r"[^\w\s-]", "", t.lower())
    return re.sub(r"\s+", "-", s).strip("-")


def inline(text: str) -> str:
    """Inline markdown -> HTML, robust against allele notation like *2/*2.

    Order matters: stash backslash-escapes and `code` spans (as final HTML)
    BEFORE escaping, then run links/bold/italic on the escaped text, then
    restore. Emphasis uses flanking rules so `*1/*36` is left literal."""
    stash: dict[str, str] = {}

    def put(rendered: str) -> str:
        key = f"{NUL}{len(stash)}{NUL}"
        stash[key] = rendered
        return key

    # 1) backslash-escaped punctuation -> literal char
    text = re.sub(r"\\([*_`\[\]()\\#~.-])", lambda m: put(escape(m.group(1))), text)
    # 2) inline code (contents are literal — never touched by emphasis)
    text = re.sub(r"`([^`]+)`", lambda m: put(f"<code>{escape(m.group(1))}</code>"), text)
    # 3) escape the remaining plain text (markdown delimiters survive)
    text = escape(text)
    # 4) links [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    # 5) bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)
    # 6) italic with flanking — won't match *allele* or path-like *x/*y
    text = re.sub(r"(?<![\w*/])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*/])", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w_])_(?!\s)([^_]+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", text)
    # 7) restore
    for k, v in stash.items():
        text = text.replace(k, v)
    return text


def md_table(lines: list[str]) -> str:
    rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines]
    if len(rows) < 2:
        return ""
    head, body = rows[0], rows[2:]  # rows[1] is the --- separator
    th = "".join(f"<th>{inline(c)}</th>" for c in head)
    trs = []
    for i, r in enumerate(body):
        cls = "even" if i % 2 else "odd"
        td = "".join(f"<td>{inline(c)}</td>" for c in r)
        trs.append(f'<tr class="{cls}">{td}</tr>')
    return f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def convert_md(md: str) -> str:
    lines = md.splitlines()
    out, i, n = [], 0, len(md.splitlines())

    def take(pred, transform):
        nonlocal i
        acc = []
        while i < n and pred(lines[i].strip()):
            acc.append(transform(lines[i].strip()))
            i += 1
        return acc

    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        if re.fullmatch(r"[-*_]{3,}", s):
            out.append("<hr>"); i += 1; continue
        m = re.match(r"^(#{1,6})\s+(.*)", s)
        if m:
            lv, txt = len(m.group(1)), m.group(2).strip()
            out.append(f'<h{lv} id="{slugify(txt)}">{inline(txt)}</h{lv}>'); i += 1; continue
        if s.startswith("|") and s.endswith("|"):
            tbl = take(lambda x: x.startswith("|") and x.endswith("|"), lambda x: x)
            out.append(md_table(tbl)); continue
        if re.match(r"^\d+\.\s", s):
            items = take(lambda x: bool(re.match(r"^\d+\.\s", x)),
                         lambda x: re.match(r"^\d+\.\s+(.*)", x).group(1))
            out.append("<ol>" + "".join(f"<li>{inline(it)}</li>" for it in items) + "</ol>"); continue
        if re.match(r"^[-*+]\s", s):
            items = take(lambda x: bool(re.match(r"^[-*+]\s", x)), lambda x: x[2:])
            out.append("<ul>" + "".join(f"<li>{inline(it)}</li>" for it in items) + "</ul>"); continue
        if s.startswith(">"):
            bq = take(lambda x: x.startswith(">"), lambda x: x[1:].lstrip())
            out.append(f"<blockquote><p>{inline(' '.join(bq))}</p></blockquote>"); continue
        para = take(lambda x: bool(x) and not re.match(
            r"^(#|\||>|\d+\.\s|[-*+]\s|-{3,}$|\*{3,}$)", x), lambda x: x)
        if para:
            out.append("<p>" + "<br>".join(inline(p) for p in para) + "</p>"); continue
        i += 1
    return "\n".join(out)


def split_doc(md: str):
    lines = md.splitlines()
    title, meta, i = "Personal Genome Report", [], 0
    while i < len(lines):
        m = re.match(r"^#\s+(.*)", lines[i].strip())
        if m:
            title = m.group(1).strip(); i += 1; break
        i += 1
    while i < len(lines):
        s = lines[i].strip()
        if re.fullmatch(r"-{3,}", s) or re.match(r"^##\s", s):
            break
        if s:
            meta.append(lines[i])
        i += 1
    bstart = next((k for k, ln in enumerate(lines) if re.match(r"^##\s", ln.strip())), 0)
    return title, "\n".join(meta), "\n".join(lines[bstart:])


def wrap_tldr(body: str) -> str:
    m = re.search(r"<h2[^>]*>[^<]*TL;DR[^<]*</h2>", body)
    if not m:
        return body
    nxt = body.find("<h2", m.end())
    nxt = len(body) if nxt == -1 else nxt
    return (body[:m.start()] + '<section class="tldr">'
            + body[m.start():nxt] + "</section>" + body[nxt:])


def build_toc(body_md: str) -> str:
    entries = [(slugify(t.strip()), t.strip()) for ln in body_md.splitlines()
               if (t := (re.match(r"^##\s+(.*)", ln.strip()) or [None, None])[1]) is not None]
    if not entries:
        return ""
    items = "".join(f'<li><a href="#{s}">{escape(t)}</a></li>' for s, t in entries)
    return f'<nav class="toc"><h2>Contents</h2><ol>{items}</ol></nav>'


CSS = """
:root{
  --bg:#06080c; --bg-card:#0c1018; --bg-grid:rgba(94,226,255,.025);
  --fg:#e8eef5; --fg-dim:rgba(232,238,245,.55); --fg-mute:rgba(232,238,245,.32);
  --accent:#5ee2ff; --accent-soft:rgba(94,226,255,.12); --accent-bright:#82ecff;
  --tier-c:#7df0a8; --warn:#ff3a4a; --warn-soft:rgba(255,58,74,.1);
  --border:rgba(232,238,245,.10); --border-strong:rgba(232,238,245,.20);
  --border-accent:rgba(94,226,255,.25);
  --font-display:'Space Grotesk','Helvetica Neue',sans-serif;
  --font-mono:'Space Mono','JetBrains Mono','Courier New',monospace;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:16px;scroll-behavior:smooth}
body{
  font-family:var(--font-display);background:var(--bg);color:var(--fg);line-height:1.65;
  background-image:linear-gradient(var(--bg-grid) 1px,transparent 1px),
    linear-gradient(90deg,var(--bg-grid) 1px,transparent 1px);
  background-size:46px 46px;
}
::selection{background:var(--accent);color:var(--bg)}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--border-strong);border-radius:5px}
::-webkit-scrollbar-track{background:transparent}

.site-header{
  position:sticky;top:0;z-index:100;background:rgba(6,8,12,.92);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  border-bottom:1px solid var(--border);padding:.7rem 1.5rem;
  display:flex;align-items:center;gap:1rem;flex-wrap:wrap;
}
.site-header .title{font-weight:700;letter-spacing:-.02em;font-size:1.02rem;color:var(--fg)}
.site-header .title .dot{color:var(--accent)}
.site-header .sample-chip{
  font-family:var(--font-mono);font-size:.74rem;color:var(--accent);
  background:var(--accent-soft);border:1px solid var(--border-accent);
  border-radius:4px;padding:.18rem .55rem;letter-spacing:.02em;
}
.disclaimer{
  width:100%;background:var(--warn-soft);border-left:3px solid var(--warn);
  color:var(--fg-dim);padding:.55rem .9rem;font-size:.79rem;border-radius:0 4px 4px 0;
}
.disclaimer strong{color:var(--warn)}

.wrap{max-width:880px;margin:0 auto;padding:2.2rem 1.5rem 5rem}

.doc-title{font-size:1.5rem;font-weight:700;letter-spacing:-.02em;color:var(--fg);margin-bottom:1.2rem}

.meta-card{
  background:var(--bg-card);border:1px solid var(--border);border-radius:8px;
  padding:1rem 1.2rem;margin-bottom:1.8rem;font-family:var(--font-mono);
  font-size:.78rem;color:var(--fg-dim);line-height:1.75;
}
.meta-card strong{color:var(--accent);font-weight:400}
.meta-card p{margin:.2rem 0}

h1,h2,h3,h4{font-family:var(--font-display);letter-spacing:-.02em}
h1{font-size:1.4rem;font-weight:700;color:var(--fg);margin:2.4rem 0 .7rem;
   padding-bottom:.4rem;border-bottom:1px solid var(--border-accent)}
h2{font-size:1.18rem;font-weight:700;color:var(--accent);margin:2.4rem 0 .7rem}
h3{font-size:1.02rem;font-weight:600;color:var(--fg);margin:1.5rem 0 .4rem}
h4,h5,h6{font-family:var(--font-mono);font-size:.78rem;text-transform:uppercase;
   letter-spacing:.07em;color:var(--fg-mute);margin:1.1rem 0 .3rem}

p{margin:.7rem 0;color:var(--fg)}
strong{color:var(--fg);font-weight:700}
em{color:var(--fg-dim);font-style:italic}
a{color:var(--accent);text-decoration:none;border-bottom:1px solid var(--border-accent)}
a:hover{color:var(--accent-bright)}
ul{margin:.6rem 0 .6rem 1.3rem}ul li{margin:.32rem 0}ul li::marker{color:var(--accent)}
ol{margin:.6rem 0 .6rem 1.4rem}ol li{margin:.36rem 0}
code{font-family:var(--font-mono);font-size:.82em;background:var(--accent-soft);
   color:var(--accent-bright);border:1px solid var(--border-accent);
   border-radius:3px;padding:.06em .34em}
hr{border:none;border-top:1px solid var(--border);margin:2.4rem 0}
blockquote{margin:.9rem 0;padding:.7rem 1rem;background:var(--warn-soft);
   border-left:3px solid var(--warn);border-radius:0 4px 4px 0;
   color:var(--fg-dim);font-size:.9rem}
blockquote strong{color:var(--warn)}

table{width:100%;border-collapse:collapse;font-size:.85rem;margin:.9rem 0 1.6rem;
   background:var(--bg-card);border:1px solid var(--border);border-radius:8px;overflow:hidden}
thead tr{background:rgba(94,226,255,.06)}
th{text-align:left;padding:.6rem .85rem;font-family:var(--font-mono);font-size:.72rem;
   text-transform:uppercase;letter-spacing:.04em;font-weight:700;color:var(--accent);
   border-bottom:1px solid var(--border-accent);white-space:nowrap}
td{padding:.6rem .85rem;vertical-align:top;border-bottom:1px solid var(--border);color:var(--fg)}
tr.even td{background:rgba(232,238,245,.02)}
tr:last-child td{border-bottom:none}

.toc{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;
   padding:1rem 1.2rem;margin-bottom:2rem}
.toc h2{font-family:var(--font-mono);font-size:.72rem;text-transform:uppercase;
   letter-spacing:.08em;color:var(--fg-mute);margin:0 0 .5rem;padding:0;border:none}
.toc ol{margin:0;padding-left:1.2rem}.toc li{margin:.26rem 0}
.toc a{color:var(--fg-dim);border:none}.toc a:hover{color:var(--accent)}

.tldr ol{counter-reset:tl;list-style:none;margin:.6rem 0;padding:0}
.tldr ol li{counter-increment:tl;display:flex;gap:.8rem;padding:.8rem 1rem;margin:.5rem 0;
   background:var(--bg-card);border:1px solid var(--border);border-left:2px solid var(--accent);
   border-radius:6px;align-items:flex-start}
.tldr ol li::before{content:counter(tl);font-family:var(--font-mono);background:var(--accent-soft);
   color:var(--accent);border:1px solid var(--border-accent);border-radius:50%;
   min-width:1.6rem;height:1.6rem;display:flex;align-items:center;justify-content:center;
   font-size:.74rem;font-weight:700;flex-shrink:0}

.site-footer{margin-top:3rem;padding:1.4rem 1.5rem;border-top:1px solid var(--border);
   text-align:center;font-family:var(--font-mono);font-size:.71rem;color:var(--fg-mute)}
.site-footer strong{color:var(--warn)}

@media(max-width:640px){
  .wrap{padding:1rem .8rem 3rem}
  table{font-size:.78rem}th,td{padding:.45rem .55rem}
  h1{font-size:1.2rem}h2{font-size:1.04rem}.doc-title{font-size:1.25rem}
}
"""

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>{title}</title>
<link href="https://api.fontshare.com/v2/css?f[]=space-grotesk@400,500,700&f[]=space-mono@400,700&display=swap" rel="stylesheet">
<style>{css}</style>
</head>
<body>
<header class="site-header">
  <span class="title"><span class="dot">&#9670;</span> Genome Report</span>
  <span class="sample-chip">{sample}</span>
  <div class="disclaimer">
    <strong>Research-grade, not diagnostic.</strong>
    Every finding is a topic to raise with a clinician &mdash; confirm actionable items with clinical-grade testing before acting.
  </div>
</header>
<div class="wrap">
  <div class="doc-title">{title}</div>
  {meta}
  {toc}
  {body}
</div>
<footer class="site-footer">
  <strong>Research-grade only &mdash; not for clinical use.</strong>
  Personal genetic data; access-controlled. Do not share or distribute.
  &nbsp;|&nbsp; Sample {sample} &nbsp;|&nbsp; Rendered {generated}
</footer>
</body>
</html>
"""


def main():
    if not MD_PATH.exists():
        print(f"ERROR: {MD_PATH} not found", file=sys.stderr)
        sys.exit(1)
    md = MD_PATH.read_text(encoding="utf-8")
    title, meta_md, body_md = split_doc(md)

    sample = "SQ8TH633"
    m = re.search(r"\*\*Sample:\*\*\s*(\S+)", meta_md)
    if m:
        sample = m.group(1).rstrip("·").strip()
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    body_html = wrap_tldr(convert_md(body_md))
    meta_html = f'<div class="meta-card">{convert_md(meta_md)}</div>' if meta_md.strip() else ""
    toc_html = build_toc(body_md)

    out = TEMPLATE.format(title=escape(title), css=CSS, sample=escape(sample),
                          meta=meta_html, toc=toc_html, body=body_html,
                          generated=escape(generated))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(out, encoding="utf-8")
    print(f"Written: {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
