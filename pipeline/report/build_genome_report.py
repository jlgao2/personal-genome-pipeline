#!/usr/bin/env python3
"""
build_genome_report.py
Reads output/health_summary.md and renders a polished, self-contained
output/specialist/genome_report.html.  Stdlib only — no pip installs.
"""

import re
import sys
import html
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MD_PATH = REPO_ROOT / "output" / "health_summary.md"
OUT_DIR = REPO_ROOT / "output" / "specialist"
OUT_PATH = OUT_DIR / "genome_report.html"

# ---------------------------------------------------------------------------
# Minimal Markdown → HTML converter
# Handles: #/##/### headings, GFM tables, **bold**, *italic*, `code`,
#          - bullet lists, > blockquotes, --- hr, links, emoji (pass-through),
#          and bare line breaks within paragraphs.
# ---------------------------------------------------------------------------

def escape(text: str) -> str:
    """HTML-escape a string but leave already-safe entities alone."""
    return html.escape(text, quote=False)


def inline(text: str) -> str:
    """Convert inline markdown within a text run."""
    # Protect backslash-escaped chars from markdown processing by
    # replacing them with a unique placeholder, then restoring after.
    PLACEHOLDER = '\x00'  # NUL — won't appear in normal text
    escapes = {}
    def stash_escape(m):
        ch = m.group(1)
        key = f'{PLACEHOLDER}{len(escapes)}{PLACEHOLDER}'
        escapes[key] = ch
        return key
    text = re.sub(r'\\([*_`\[\]()\\#])', stash_escape, text)

    # Links: [text](url)
    text = re.sub(
        r'\[([^\]]+)\]\(([^)]+)\)',
        lambda m: f'<a href="{escape(m.group(2))}">{escape(m.group(1))}</a>',
        text
    )
    # Bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic: *text* or _text_  (single — must come after bold)
    text = re.sub(r'\*([^*\n]+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'_([^_\n]+?)_', r'<em>\1</em>', text)
    # Inline code: `code`
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Restore escaped chars
    for key, ch in escapes.items():
        text = text.replace(key, ch)
    return text


def md_table_to_html(lines: list[str]) -> str:
    """Convert a GFM table (list of raw lines) to an HTML table."""
    rows = []
    for line in lines:
        # Strip leading/trailing pipe and split
        line = line.strip().strip('|')
        cells = [c.strip() for c in line.split('|')]
        rows.append(cells)

    if len(rows) < 2:
        return ''

    header_row = rows[0]
    # rows[1] is the separator --- row; skip it
    data_rows = rows[2:]

    th_cells = ''.join(f'<th>{inline(escape(c))}</th>' for c in header_row)
    thead = f'<thead><tr>{th_cells}</tr></thead>'

    tbody_rows = []
    for i, row in enumerate(data_rows):
        cls = 'odd' if i % 2 == 0 else 'even'
        td_cells = ''.join(f'<td>{inline(escape(c))}</td>' for c in row)
        tbody_rows.append(f'<tr class="{cls}">{td_cells}</tr>')
    tbody = f'<tbody>{"".join(tbody_rows)}</tbody>'

    return f'<table>{thead}{tbody}</table>'


def convert_md(md: str) -> str:
    """Convert full markdown document to HTML body content."""
    lines = md.splitlines()
    out = []
    i = 0

    # Collect a GFM table block starting at index i; return (html, next_i)
    def collect_table(start: int):
        table_lines = []
        j = start
        while j < len(lines):
            stripped = lines[j].strip()
            if stripped.startswith('|') and stripped.endswith('|'):
                table_lines.append(lines[j])
                j += 1
            else:
                break
        return table_lines, j

    # Collect a list block starting at index i
    def collect_list(start: int):
        items = []
        j = start
        while j < len(lines):
            stripped = lines[j].strip()
            if re.match(r'^[-*+]\s', stripped):
                items.append(stripped[2:])
                j += 1
            else:
                break
        return items, j

    # Collect an ordered list block starting at index i
    def collect_olist(start: int):
        items = []
        j = start
        while j < len(lines):
            stripped = lines[j].strip()
            m = re.match(r'^\d+\.\s+(.*)', stripped)
            if m:
                items.append(m.group(1))
                j += 1
            else:
                break
        return items, j

    # Collect a blockquote block
    def collect_blockquote(start: int):
        bq_lines = []
        j = start
        while j < len(lines):
            stripped = lines[j].strip()
            if stripped.startswith('>'):
                bq_lines.append(stripped[1:].lstrip())
                j += 1
            else:
                break
        return bq_lines, j

    # Collect a paragraph block (non-empty lines that aren't special)
    def collect_para(start: int):
        para_lines = []
        j = start
        while j < len(lines):
            ln = lines[j]
            stripped = ln.strip()
            # Stop conditions
            if (not stripped
                    or stripped.startswith('#')
                    or stripped.startswith('|')
                    or re.match(r'^[-*+]\s', stripped)
                    or re.match(r'^\d+\.\s', stripped)
                    or stripped.startswith('>')
                    or re.fullmatch(r'-{3,}', stripped)
                    or re.fullmatch(r'\*{3,}', stripped)):
                break
            para_lines.append(stripped)
            j += 1
        return para_lines, j

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip blank lines
        if not stripped:
            i += 1
            continue

        # Horizontal rule (--- or ***)
        if re.fullmatch(r'[-*]{3,}', stripped):
            out.append('<hr>')
            i += 1
            continue

        # Headings
        m = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            # Generate a slug id for anchor linking
            slug = re.sub(r'[^\w\s-]', '', text.lower())
            slug = re.sub(r'\s+', '-', slug).strip('-')
            out.append(f'<h{level} id="{slug}">{inline(escape(text))}</h{level}>')
            i += 1
            continue

        # GFM Table (line starts and ends with |)
        if stripped.startswith('|') and stripped.endswith('|'):
            table_lines, i = collect_table(i)
            out.append(md_table_to_html(table_lines))
            continue

        # Ordered list
        if re.match(r'^\d+\.\s', stripped):
            items, i = collect_olist(i)
            li_items = ''.join(f'<li>{inline(escape(item))}</li>' for item in items)
            out.append(f'<ol>{li_items}</ol>')
            continue

        # Unordered list
        if re.match(r'^[-*+]\s', stripped):
            items, i = collect_list(i)
            li_items = ''.join(f'<li>{inline(escape(item))}</li>' for item in items)
            out.append(f'<ul>{li_items}</ul>')
            continue

        # Blockquote
        if stripped.startswith('>'):
            bq_lines, i = collect_blockquote(i)
            bq_content = ' '.join(bq_lines)
            out.append(f'<blockquote><p>{inline(escape(bq_content))}</p></blockquote>')
            continue

        # Paragraph
        para_lines, i = collect_para(i)
        if para_lines:
            content = '<br>'.join(inline(escape(ln)) for ln in para_lines)
            out.append(f'<p>{content}</p>')
            continue

        # Fallback: advance
        i += 1

    return '\n'.join(out)


# ---------------------------------------------------------------------------
# Split health_summary.md into a header meta block + sections
# ---------------------------------------------------------------------------

def extract_meta(md: str) -> tuple[str, str]:
    """Return (meta_block, rest) where meta_block is the first para."""
    # The first non-heading content before the first --- or ## heading
    lines = md.splitlines()
    meta_lines = []
    rest_start = 0
    for idx, ln in enumerate(lines):
        stripped = ln.strip()
        if not stripped:
            if meta_lines:
                rest_start = idx
                break
            continue
        if stripped.startswith('#') and len(stripped) > 1 and stripped[1] != '#':
            # top-level heading — keep for rest
            rest_start = idx
            break
        meta_lines.append(ln)
    rest = '\n'.join(lines[rest_start:])
    return '\n'.join(meta_lines), rest


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
/* ===== Reset & base ===== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:          #f7f8fa;
  --surface:     #ffffff;
  --border:      #e2e5ea;
  --text:        #1a1e27;
  --text-muted:  #5a6070;
  --accent:      #1a4f8a;    /* deep medical blue */
  --accent-lt:   #eef3fa;
  --warn-bg:     #fff8e7;
  --warn-border: #e0a800;
  --warn-text:   #7a5200;
  --ok-bg:       #edfaf0;
  --ok-border:   #2e8a4f;
  --ok-text:     #1a5730;
  --hr:          #d0d5de;
  --th-bg:       #f0f4fa;
  --tr-odd:      #ffffff;
  --tr-even:     #f7f9fc;
  --code-bg:     #f3f4f6;
  --disclaimer:  #4a1010;
  --disclaimer-bg: #fff0f0;
  --disclaimer-border: #cc3333;
}

html { font-size: 16px; scroll-behavior: smooth; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
               "Helvetica Neue", Arial, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.65;
}

/* ===== Sticky header ===== */
.site-header {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--accent);
  color: #fff;
  padding: 0.75rem 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.site-header .title {
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: 0.01em;
  white-space: nowrap;
}
.site-header .sample-chip {
  background: rgba(255,255,255,0.18);
  border-radius: 4px;
  padding: 0.15rem 0.6rem;
  font-size: 0.82rem;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

/* ===== Disclaimer banner ===== */
.disclaimer-banner {
  background: var(--disclaimer-bg);
  border-left: 4px solid var(--disclaimer-border);
  color: var(--disclaimer);
  padding: 0.65rem 1rem 0.65rem 1.1rem;
  font-size: 0.85rem;
  font-weight: 500;
  width: 100%;
}
.disclaimer-banner strong { color: var(--disclaimer); }

/* ===== Layout ===== */
.page-wrap {
  max-width: 860px;
  margin: 0 auto;
  padding: 2rem 1.5rem 4rem;
}

/* ===== Meta card (sample info) ===== */
.meta-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem 1.2rem;
  margin-bottom: 2rem;
  font-size: 0.88rem;
  color: var(--text-muted);
  line-height: 1.7;
}
.meta-card strong { color: var(--text); }

/* ===== Headings ===== */
h1 {
  font-size: 1.7rem;
  font-weight: 700;
  color: var(--accent);
  margin: 2rem 0 0.6rem;
  padding-bottom: 0.3rem;
  border-bottom: 2px solid var(--accent);
}
h2 {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--accent);
  margin: 2rem 0 0.6rem;
  padding-bottom: 0.25rem;
  border-bottom: 1.5px solid var(--border);
}
h3 {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
  margin: 1.4rem 0 0.4rem;
}
h4, h5, h6 {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-muted);
  margin: 1rem 0 0.3rem;
}

/* ===== Paragraph / list / blockquote ===== */
p { margin: 0.6rem 0; }

ul {
  margin: 0.5rem 0 0.5rem 1.4rem;
  padding: 0;
}
ul li { margin: 0.3rem 0; }
ul li::marker { color: var(--accent); }

ol {
  margin: 0.5rem 0 0.5rem 1.5rem;
}
ol li { margin: 0.35rem 0; }

blockquote {
  margin: 0.8rem 0;
  padding: 0.6rem 1rem;
  background: var(--warn-bg);
  border-left: 4px solid var(--warn-border);
  color: var(--warn-text);
  border-radius: 0 4px 4px 0;
  font-size: 0.9rem;
}
blockquote p { margin: 0; }

code {
  background: var(--code-bg);
  border-radius: 3px;
  padding: 0.1em 0.35em;
  font-size: 0.85em;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  color: #c0392b;
}

hr {
  border: none;
  border-top: 1px solid var(--hr);
  margin: 2rem 0;
}

/* ===== Tables ===== */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.88rem;
  margin: 0.8rem 0 1.4rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
thead tr {
  background: var(--th-bg);
}
th {
  text-align: left;
  padding: 0.6rem 0.85rem;
  font-weight: 700;
  color: var(--accent);
  border-bottom: 2px solid var(--border);
  white-space: nowrap;
}
td {
  padding: 0.55rem 0.85rem;
  vertical-align: top;
  border-bottom: 1px solid var(--border);
}
tr.odd  td { background: var(--tr-odd); }
tr.even td { background: var(--tr-even); }
tr:last-child td { border-bottom: none; }

/* ===== Callout coloring for ⚠ / ✅ markers ===== */
.warn-callout {
  background: var(--warn-bg);
  border-left: 3px solid var(--warn-border);
  padding: 0.6rem 0.9rem;
  border-radius: 0 4px 4px 0;
  margin: 0.4rem 0;
  color: var(--warn-text);
}
.ok-callout {
  background: var(--ok-bg);
  border-left: 3px solid var(--ok-border);
  padding: 0.6rem 0.9rem;
  border-radius: 0 4px 4px 0;
  margin: 0.4rem 0;
  color: var(--ok-text);
}

/* ===== TOC nav ===== */
.toc {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 1rem 1.2rem;
  margin-bottom: 2rem;
  font-size: 0.9rem;
}
.toc h2 {
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-muted);
  margin: 0 0 0.5rem;
  padding: 0;
  border: none;
}
.toc ol { margin: 0; padding-left: 1.3rem; }
.toc li { margin: 0.25rem 0; }
.toc a { color: var(--accent); text-decoration: none; }
.toc a:hover { text-decoration: underline; }

/* ===== TL;DR section styling ===== */
.tldr-section ol {
  counter-reset: tldr-counter;
  list-style: none;
  margin: 0.5rem 0;
  padding: 0;
}
.tldr-section ol li {
  counter-increment: tldr-counter;
  display: flex;
  gap: 0.75rem;
  padding: 0.7rem 1rem;
  margin: 0.5rem 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  align-items: flex-start;
}
.tldr-section ol li::before {
  content: counter(tldr-counter);
  background: var(--accent);
  color: #fff;
  border-radius: 50%;
  min-width: 1.5rem;
  height: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.78rem;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 0.1rem;
}

/* ===== Footer ===== */
.site-footer {
  margin-top: 3rem;
  padding: 1.2rem 1.5rem;
  background: var(--surface);
  border-top: 1px solid var(--border);
  text-align: center;
  font-size: 0.78rem;
  color: var(--text-muted);
}
.site-footer strong { color: var(--disclaimer); }

/* ===== Responsive ===== */
@media (max-width: 640px) {
  .page-wrap { padding: 1rem 0.8rem 3rem; }
  table { font-size: 0.8rem; }
  th, td { padding: 0.45rem 0.6rem; }
  h1 { font-size: 1.35rem; }
  h2 { font-size: 1.1rem; }
}
"""

# ---------------------------------------------------------------------------
# Section-aware rendering: wrap TL;DR in a special div, etc.
# ---------------------------------------------------------------------------

def build_toc_html(sections: list[tuple[str, str]]) -> str:
    """Build a TOC from (slug, label) pairs."""
    items = ''.join(f'<li><a href="#{slug}">{escape(label)}</a></li>'
                    for slug, label in sections)
    return f'<nav class="toc"><h2>Contents</h2><ol>{items}</ol></nav>'


def render_body(md_content: str) -> str:
    """
    Parse sections from the markdown and produce body HTML, with the
    TL;DR section wrapped in a special styled div.
    """
    # Split into lines, detect ## section starts
    lines = md_content.splitlines()

    # Identify top-level heading for the document title
    title = "Personal Genome Report"
    sample = "SQ8TH633"
    for ln in lines:
        m = re.match(r'^#\s+(.*)', ln.strip())
        if m:
            title = m.group(1).strip()
            break

    # Find all ## headings for TOC
    toc_entries = []
    for ln in lines:
        m = re.match(r'^##\s+(.*)', ln.strip())
        if m:
            text = m.group(1).strip()
            slug = re.sub(r'[^\w\s-]', '', text.lower())
            slug = re.sub(r'\s+', '-', slug).strip('-')
            toc_entries.append((slug, text))

    toc_html = build_toc_html(toc_entries) if toc_entries else ''

    # Convert full body
    body_html = convert_md(md_content)

    # Post-process: wrap the TL;DR h2 section in a styled div
    body_html = re.sub(
        r'(<h2[^>]*>TL;DR[^<]*</h2>)',
        r'<div class="tldr-section">\1',
        body_html
    )
    # Close the tldr-section div before the next h2
    first_non_tldr_h2 = re.search(
        r'<h2(?!.*TL;DR)[^>]*>(?!TL;DR)',
        body_html[body_html.find('tldr-section'):] if 'tldr-section' in body_html else body_html
    )
    if 'tldr-section' in body_html:
        # Find position of second h2 after the tldr-section div
        tldr_pos = body_html.find('<div class="tldr-section">')
        next_h2 = body_html.find('<h2', tldr_pos + 10)
        next_h2_after = body_html.find('<h2', next_h2 + 4)
        if next_h2_after != -1:
            body_html = body_html[:next_h2_after] + '</div>' + body_html[next_h2_after:]
        else:
            body_html += '</div>'

    return title, sample, toc_html, body_html


# ---------------------------------------------------------------------------
# Full HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex,nofollow">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>

<header class="site-header">
  <span class="title">Personal Genome Report</span>
  <span class="sample-chip">{sample}</span>
  <div class="disclaimer-banner">
    <strong>Research-grade, not diagnostic.</strong>
    Every finding below is a topic to raise with a clinician — not a diagnosis.
    Confirm actionable items with clinical-grade testing before acting.
  </div>
</header>

<div class="page-wrap">

{meta_card}

{toc}

{body}

</div>

<footer class="site-footer">
  <strong>Research-grade only &mdash; not for clinical use.</strong>
  This report contains personal genetic data and is access-controlled.
  Do not share, screenshot, or distribute.
  &nbsp;|&nbsp; Sample: {sample} &nbsp;|&nbsp; Generated: {generated}
</footer>

</body>
</html>
"""


def build_meta_card(meta_md: str) -> str:
    """Render the sample metadata block as a styled card."""
    converted = convert_md(meta_md)
    return f'<div class="meta-card">{converted}</div>'


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not MD_PATH.exists():
        print(f"ERROR: {MD_PATH} not found", file=sys.stderr)
        sys.exit(1)

    md_raw = MD_PATH.read_text(encoding="utf-8")

    # Split header meta from body
    meta_md, body_md = extract_meta(md_raw)

    # Extract generated date from meta if present
    generated = "2026-06-08"
    m = re.search(r'\*\*Generated:\*\*\s*([\d-]+)', meta_md)
    if m:
        generated = m.group(1)

    # Extract sample ID
    sample = "SQ8TH633"
    m2 = re.search(r'\*\*Sample:\*\*\s*(\S+)', meta_md)
    if m2:
        sample = m2.group(1).rstrip('·').strip()

    title, _sample, toc_html, body_html = render_body(body_md)

    meta_card_html = build_meta_card(meta_md)

    html_out = HTML_TEMPLATE.format(
        title=escape(title),
        css=CSS,
        sample=escape(sample),
        meta_card=meta_card_html,
        toc=toc_html,
        body=body_html,
        generated=escape(generated),
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_out, encoding="utf-8")
    print(f"Written: {OUT_PATH}  ({OUT_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
