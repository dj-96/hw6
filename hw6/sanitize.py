"""Code-level defense: clean a vendor document before any model sees it.

The rule: the model should read what a person would see, nothing more.
- HTML: drop comments, <script>/<style>, and elements hidden with CSS
  (display:none, visibility:hidden, font-size ~0, white/transparent text, opacity:0,
  pushed off-screen, clipped away), whether the CSS is inline or in a <style> rule.
- PDF: keep only text that is drawn on the page, at a readable size, in a
  non-white color, and not in an invisible text render mode (3 or 7).
- Email: use the plain-text part; if there is only HTML, clean it as above.
- Everything: Unicode NFKC, remove zero-width and control characters.

Each function returns (clean_text, removed) where `removed` lists the hidden
snippets that were dropped, for the audit trail. Removed text is never shown
to the model.
"""
import email
import re
import unicodedata
from email import policy
from html.parser import HTMLParser
from pathlib import Path

from pypdf import PdfReader

MIN_PDF_FONT_PT = 4.0  # anything smaller is not readable on a printed page
INVISIBLE_CHARS = re.compile(r"[​-‏‪-‮⁠-⁤﻿­]")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# CSS that makes an element invisible to a person.
HIDDEN_CSS = [
    re.compile(r"display\s*:\s*none", re.I),
    re.compile(r"visibility\s*:\s*hidden", re.I),
    re.compile(r"opacity\s*:\s*0(?:\.0*)?\s*(?:;|$)", re.I),
    re.compile(r"font-size\s*:\s*(?:0+(?:\.0+)?(?:px|pt|em|rem|%)?|[0-2](?:\.\d+)?(?:px|pt)|0?\.[0-2]\d*(?:em|rem))\s*(?:;|$|!)", re.I),
    re.compile(r"(?<![-\w])color\s*:\s*(?:#fff(?:fff)?\b|white\b|transparent\b|rgba?\(\s*255\s*,\s*255\s*,\s*255)", re.I),
    re.compile(r"(?:height|width)\s*:\s*0(?:px)?\s*(?:;|$)", re.I),
    # Pushed off-screen or clipped away (added after the Problem 7 red team).
    re.compile(r"(?<![-\w])(?:left|top|right|bottom|text-indent|margin-left|margin-top)\s*:\s*-\d{3,}", re.I),
    re.compile(r"clip\s*:\s*rect\(\s*0", re.I),
    re.compile(r"clip-path\s*:\s*inset\(\s*(?:50|100)%", re.I),
    re.compile(r"transform\s*:\s*scale\(\s*0(?:\.0+)?\s*\)", re.I),
]
STYLE_BLOCK = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
CSS_RULE = re.compile(r"([^{}]+)\{([^}]*)\}")
SIMPLE_SELECTOR = re.compile(r"^([a-z][a-z0-9]*)?(?:([.#])([\w-]+))?$", re.I)


def hidden_selectors(html: str) -> list[tuple[str | None, str | None, str | None]]:
    """(tag, kind, name) for every simple <style> rule whose CSS hides an element."""
    found = []
    for block in STYLE_BLOCK.findall(html):
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        for selectors, body in CSS_RULE.findall(block):
            if not any(p.search(body.strip()) for p in HIDDEN_CSS):
                continue
            for sel in selectors.split(","):
                m = SIMPLE_SELECTOR.match(sel.strip())
                if m and (m.group(1) or m.group(3)):
                    found.append((m.group(1), m.group(2), m.group(3)))
    return found
VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "wbr", "col", "area", "base", "source"}
BLOCK_TAGS = {"p", "br", "tr", "div", "li", "h1", "h2", "h3", "h4", "header", "footer", "table", "section"}


def clean_chars(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = INVISIBLE_CHARS.sub("", text)
    return CONTROL_CHARS.sub("", text)


def _tidy(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class _VisibleText(HTMLParser):
    def __init__(self, hidden_rules=()) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_rules = list(hidden_rules)
        self.parts: list[str] = []
        self.removed: list[str] = []
        self._stack: list[tuple[str, bool]] = []  # (tag, hidden)
        self._hidden_buf: list[str] = []

    @property
    def _hidden(self) -> bool:
        return any(h for _, h in self._stack)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        style = a.get("style") or ""
        hidden = (
            tag in ("script", "style", "template", "noscript", "head")
            or "hidden" in a
            or a.get("aria-hidden") == "true"
            or any(p.search(style) for p in HIDDEN_CSS)
            or self._matches_hidden_rule(tag, a)
        )
        if tag in VOID_TAGS:
            if tag == "br" and not self._hidden:
                self.parts.append("\n")
            return
        if hidden and not self._hidden and tag not in ("script", "style", "head"):
            self._hidden_buf = []
        self._stack.append((tag, hidden))
        if tag in BLOCK_TAGS and not self._hidden:
            self.parts.append("\n")

    def _matches_hidden_rule(self, tag, a) -> bool:
        classes = (a.get("class") or "").split()
        for rtag, kind, name in self.hidden_rules:
            if rtag and rtag != tag:
                continue
            if kind == "." and name not in classes:
                continue
            if kind == "#" and a.get("id") != name:
                continue
            return True
        return False

    def handle_endtag(self, tag):
        # Pop back to the matching tag (tolerates sloppy HTML).
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                was_hidden = self._hidden
                del self._stack[i:]
                if was_hidden and not self._hidden and self._hidden_buf:
                    self.removed.append(_tidy(" ".join(self._hidden_buf)))
                    self._hidden_buf = []
                break
        if tag in ("td", "th") and not self._hidden:
            self.parts.append(" ")
        elif tag in BLOCK_TAGS and not self._hidden:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._hidden:
            # Only log text hidden by CSS/attributes; <head>, <script>, <style> are normal page plumbing.
            plumbing = any(t in ("script", "style", "head", "template", "noscript") for t, _ in self._stack)
            if not plumbing and data.strip():
                self._hidden_buf.append(data)
        else:
            self.parts.append(data)

    def handle_comment(self, data):
        if data.strip():
            self.removed.append("<!-- " + _tidy(data) + " -->")


def sanitize_html(html: str) -> tuple[str, list[str]]:
    parser = _VisibleText(hidden_selectors(html))
    parser.feed(html)
    parser.close()
    return _tidy(clean_chars("".join(parser.parts))), [clean_chars(r) for r in parser.removed if r]


def sanitize_pdf(path: Path) -> tuple[str, list[str]]:
    kept: list[str] = []
    removed: list[str] = []
    for page in PdfReader(path).pages:
        x0, y0, x1, y1 = (float(v) for v in page.mediabox)
        fill = [(0.0, 0.0, 0.0)]  # current fill color (RGB), with q/Q save/restore
        render = [0]  # text render mode; 3 = invisible, 7 = clip only (also invisible)

        def before(op, args, cm, tm):
            if op == b"rg" and len(args) == 3:
                fill[-1] = tuple(float(a) for a in args)
            elif op == b"g" and len(args) == 1:
                fill[-1] = (float(args[0]),) * 3
            elif op == b"Tr" and len(args) == 1:
                render[-1] = int(args[0])
            elif op == b"q":
                fill.append(fill[-1])
                render.append(render[-1])
            elif op == b"Q" and len(fill) > 1:
                fill.pop()
                render.pop()

        def on_text(text, cm, tm, font_dict, font_size):
            if not text.strip():
                kept.append(text)
                return
            # Position and size on the page = text matrix combined with the CTM.
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            scale = (abs(tm[3] * cm[3]) or abs(tm[0] * cm[0]) or 1.0)
            size = (font_size or 0) * scale
            why = None
            if render[-1] in (3, 7):
                why = f"invisible render mode {render[-1]}"
            elif size < MIN_PDF_FONT_PT:
                why = f"tiny text {size:.1f}pt"
            elif not (x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1):
                why = f"off-page at ({x:.0f},{y:.0f})"
            elif min(fill[-1]) >= 0.95:
                why = "white text"
            if why:
                removed.append(f"[{why}] {text.strip()}")
            else:
                kept.append(text)

        page.extract_text(visitor_operand_before=before, visitor_text=on_text)
        kept.append("\n")
    return _tidy(clean_chars("".join(kept))), [clean_chars(r) for r in removed]


def sanitize_eml(path: Path) -> tuple[str, list[str]]:
    msg = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    header = "\n".join(f"{h}: {msg[h]}" for h in ("From", "To", "Subject", "Date") if msg[h])
    removed: list[str] = []
    plain = msg.get_body(preferencelist=("plain",))
    html = msg.get_body(preferencelist=("html",))
    if plain is not None:
        body = clean_chars(plain.get_content())
        if html is not None:
            # The HTML part is what an email app shows. Anything it hides is suspicious: log it.
            _, html_removed = sanitize_html(html.get_content())
            removed += [f"[hidden in HTML part] {r}" for r in html_removed]
    elif html is not None:
        body, removed = sanitize_html(html.get_content())
    else:
        body = ""
    return f"{clean_chars(header)}\n\n{_tidy(body)}", removed


def sanitize_document(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm"):
        return sanitize_html(path.read_text(encoding="utf-8"))
    if suffix == ".pdf":
        return sanitize_pdf(path)
    if suffix == ".eml":
        return sanitize_eml(path)
    raise ValueError(f"unsupported file type {suffix!r}")
