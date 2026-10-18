"""Design-level defense: Python, not the model, makes the purchasing decision.

The model only extracts facts. This module then:
1. grounds each fact: the value must literally appear in the document text the
   model was given, or it becomes unknown (None);
2. scans the document for removed/pending vendor names;
3. applies the four handbook checks (section 4) against the approved vendor
   list (section 5), the removed list (section 6), and the catalogue (section 9);
4. writes the reason sentence itself, so no text from the document (links,
   instructions) can reach the final answer.

All lists are parsed from data/shop_handbook.md, so the handbook stays the
single source of truth.
"""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from models import VendorDecision

HANDBOOK_PATH = Path(__file__).resolve().parent / "data" / "shop_handbook.md"
MAX_LEAD_DAYS = 21
MAX_MIN_ORDER = 600


@dataclass(frozen=True)
class Handbook:
    approved: dict[str, str]  # normalized name -> display name
    removed: dict[str, str]  # display name -> status
    max_cost: dict[str, float]  # SKU -> max unit cost


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def _section(text: str, number: int) -> str:
    m = re.search(rf"^## {number}\..*?(?=^## \d+\.|\Z)", text, re.S | re.M)
    return m.group(0) if m else ""


def _rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if line.startswith("|") and not re.match(r"^\|\s*-", line):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]  # drop header row


@lru_cache(maxsize=1)
def handbook() -> Handbook:
    text = HANDBOOK_PATH.read_text(encoding="utf-8")
    approved = {_norm(r[1]): r[1] for r in _rows(_section(text, 5))}
    removed = {r[0]: r[1] for r in _rows(_section(text, 6))}
    max_cost = {r[0]: float(r[4].lstrip("$")) for r in _rows(_section(text, 9))}
    return Handbook(approved, removed, max_cost)


# --- Grounding: a fact must be in the document ------------------------------

def _price_in(text: str, price: float) -> bool:
    return re.search(rf"\$?\s?{re.escape(f'{price:,.2f}')}(?!\d)", text) is not None or (
        price == int(price) and re.search(rf"\$\s?{int(price):,}(?![\d.])", text) is not None
    )


def _int_in(text: str, n: int) -> bool:
    return re.search(rf"(?<![\d.,$]){n:,}(?![\d,]|\.\d)|(?<![\d.,$]){n}(?![\d,]|\.\d)", text) is not None


def ground(facts: VendorDecision, doc_text: str) -> tuple[VendorDecision, list[str]]:
    """Blank out any extracted value that does not appear in the document text."""
    notes = []
    f = facts.model_copy()
    if f.sku and f.sku not in doc_text:
        notes.append(f"SKU {f.sku} not found in document")
        f.sku = None
    if f.unit_price is not None and not _price_in(doc_text, f.unit_price):
        notes.append(f"unit price {f.unit_price} not found in document")
        f.unit_price = None
    if f.lead_time_days is not None and not _int_in(doc_text, f.lead_time_days):
        notes.append(f"lead time {f.lead_time_days} not found in document")
        f.lead_time_days = None
    if f.min_order is not None and not _int_in(doc_text, f.min_order):
        notes.append(f"minimum order {f.min_order} not found in document")
        f.min_order = None
    return f, notes


# --- The four checks --------------------------------------------------------

def decide(facts: VendorDecision, doc_text: str) -> tuple[VendorDecision, list[str]]:
    """Return the final answer with a code-made decision and reason, plus design notes."""
    hb = handbook()
    f, notes = ground(facts, doc_text)
    lower = doc_text.lower()

    def result(decision: str, reason: str) -> tuple[VendorDecision, list[str]]:
        return f.model_copy(update={"decision": decision, "reason": reason}), notes

    # Check 1: approved vendor. A removed vendor named anywhere in the document fails,
    # even if the model was talked into reporting a different vendor.
    banned = [name for name in hb.removed if name.lower() in lower]
    if banned or _norm(f.vendor) in {_norm(n) for n in hb.removed}:
        name = banned[0] if banned else f.vendor
        if banned and _norm(f.vendor) != _norm(name):
            notes.append(f"model reported vendor {f.vendor!r} but document names removed vendor {name!r}")
        return result("do_not_recommend", f"Approved vendor check failed: {name} is on the removed/pending vendor list.")
    if _norm(f.vendor) not in hb.approved:
        return result("do_not_recommend", f"Approved vendor check failed: {f.vendor} is not on the approved vendor list.")
    if f.vendor.lower() not in lower:
        notes.append(f"vendor name {f.vendor!r} not found in document")
        return result("do_not_recommend", f"Approved vendor check failed: the vendor name {f.vendor} does not appear in the document.")

    # Check 2: price at or below the catalogue max unit cost.
    if f.sku is None or f.sku not in hb.max_cost:
        return result("do_not_recommend", "Price check failed: the document has no Campus Customs SKU we can match to the catalogue.")
    cap = hb.max_cost[f.sku]
    if f.unit_price is None:
        return result("do_not_recommend", f"Price check failed: the unit price for {f.sku} is unknown.")
    if f.unit_price > cap:
        return result("do_not_recommend", f"Price check failed: ${f.unit_price:.2f} is above the max unit cost for {f.sku}.")

    # Check 3: lead time.
    if f.lead_time_days is None:
        return result("do_not_recommend", "Lead time check failed: the lead time is unknown.")
    if f.lead_time_days > MAX_LEAD_DAYS:
        return result("do_not_recommend", f"Lead time check failed: {f.lead_time_days} days is over the {MAX_LEAD_DAYS}-day limit.")

    # Check 4: minimum order.
    if f.min_order is None:
        return result("do_not_recommend", "Minimum order check failed: the minimum order is unknown.")
    if f.min_order > MAX_MIN_ORDER:
        return result("do_not_recommend", f"Minimum order check failed: {f.min_order} units is over the {MAX_MIN_ORDER}-unit limit.")

    return result("recommend", "All four purchasing checks passed: approved vendor, price at or below max unit cost, lead time within 21 days, and minimum order within 600 units.")
