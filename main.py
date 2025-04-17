# main.py
"""FastAPI PDF bank‑statement parser.
   Core logic only – parsing rules live in `rules.py` so we can add new
   banks without touching this file.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import List, Tuple, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextLineHorizontal, LTChar

from rules import PARSING_RULES  # <-- 🔑 lives in separate file now

app = FastAPI()

# ─────────────────────────────── helpers ──────────────────────────────

NumberParts = Tuple[str, str, bool]  # digits, decimals, is_negative

def normalize_amount_string(raw: str, th_sep: str, dec_sep: str,
                             trailing_neg: str) -> str:
    """Turn a raw string extracted from PDF into a Python‑parsable number."""
    raw = raw.strip()
    neg = False
    if trailing_neg == "Y" and raw.endswith("-"):
        neg, raw = True, raw[:-1].strip()
    if trailing_neg == "N" and raw.endswith("N"):
        neg, raw = True, raw[:-1].strip()

    raw = raw.replace(th_sep, "")
    raw = raw.replace(dec_sep, ".")
    # guard
    if re.fullmatch(r"[0-9.]+", raw) is None:
        raise ValueError(f"bad amount token: {raw}")
    return f"-{raw}" if neg else raw


def safe_parse_amount(token: Optional[str], fmt: dict) -> Optional[float]:
    if not token:
        return None
    try:
        return float(normalize_amount_string(token,
                                             fmt["thousands_separator"],
                                             fmt["decimal_separator"],
                                             fmt["negative_trailing"]))
    except Exception:
        return None


def first_page_strings(pdf_path: str, max_lines: int = 40) -> List[str]:
    lines: List[str] = []
    for page_num, page in enumerate(extract_pages(pdf_path)):
        if page_num > 0:
            break
        for obj in page:
            if isinstance(obj, LTTextLineHorizontal):
                text = obj.get_text().strip()
                if text:
                    lines.append(re.sub(r"\s+", " ", text))
                    if len(lines) >= max_lines:
                        break
        break
    return lines


def detect_rule(first_page: List[str]) -> str:
    joined = " ".join(first_page).upper()
    if "ABSA" in joined and "CHEQUE ACCOUNT" in joined:
        return "ABSA_CHEQUE_ACCOUNT_STATEMENT"
    if "STANDARD BANK" in joined and "BUSINESS CURRENT ACCOUNT" in joined:
        return "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT"
    raise HTTPException(400, detail="Unsupported or undetected bank/account type")


# ─────────────────────────────── extraction ───────────────────────────

def combine_column_values(xmap: List[Tuple[float, str]], zone: Tuple[int, int]) -> str:
    lo, hi = zone
    vals = [w for x, w in xmap if lo <= x <= hi]
    return " ".join(vals) if vals else ""


def parse_pdf_to_transactions(filepath: str, rule_name: str) -> List[dict]:
    rule = PARSING_RULES[rule_name]
    zones = rule["column_zones"]
    fmt = rule["amount_format"]
    date_x_thresh = rule.get("date_x_threshold", 0)

    transactions: List[dict] = []

    for page in extract_pages(filepath):
        # build per‑line x‑map
        current_line_items: List[Tuple[float, str]] = []
        current_y: Optional[float] = None

        def flush_line():
            nonlocal current_line_items, current_y
            if not current_line_items:
                return
            xmap = sorted(current_line_items, key=lambda t: t[0])
            desc = combine_column_values(xmap, zones["description"]).strip()
            debit_t = combine_column_values(xmap, zones["debit"]).strip()
            credit_t = combine_column_values(xmap, zones["credit"]).strip()
            bal_t = combine_column_values(xmap, zones["balance"]).strip()
            date_token = next((w for x, w in xmap if x >= date_x_thresh), "")

            debit = safe_parse_amount(debit_t, fmt)
            credit = safe_parse_amount(credit_t, fmt)
            balance = safe_parse_amount(bal_t, fmt)

            # heuristics – skip header/footer junk
            if not desc or (not debit and not credit):
                current_line_items = []
                return
            try:
                dt = parse_date(date_token, rule["date_format"], first_year_from_doc)
            except Exception:
                current_line_items = []
                return

            transactions.append({
                "date": dt.strftime("%Y-%m-%d"),
                "description": desc,
                "amount": credit if credit is not None else -debit if debit is not None else 0.0,
                "balance": balance,
            })
            current_line_items = []

        # fetch statement year for date completion (Std Bank only)
        first_year_from_doc = extract_year_from_doc(filepath)

        for obj in page:
            if isinstance(obj, LTTextLineHorizontal):
                y = round(obj.y0, 1)
                if current_y is None:
                    current_y = y
                # new line starts when Y differs significantly
                if abs(y - current_y) > 2:
                    flush_line()
                    current_y = y
                for char_obj in obj:
                    if isinstance(char_obj, LTChar):
                        continue
                text = obj.get_text().strip()
                if text:
                    # record each word & its x position
                    for w in re.split(r"\s+", text):
                        x_pos = obj.x0 + text.find(w) * 1.0  # rough → good enough for zones
                        current_line_items.append((x_pos, w))
        flush_line()

    return transactions


# helpers for dates & years ------------------------------------------------

def extract_year_from_doc(pdf_path: str) -> int:
    lines = first_page_strings(pdf_path, 100)
    m = re.search(r"\b(20\d{2})\b", " ".join(lines))
    return int(m.group(1)) if m else datetime.today().year


def parse_date(token: str, date_rule: dict, fallback_year: int) -> datetime:
    for fmt in date_rule["formats"]:
        try:
            dt = datetime.strptime(token, fmt)
            if date_rule.get("year_optional") == "Y":
                dt = dt.replace(year=fallback_year)
            return dt
        except ValueError:
            continue
    raise ValueError("bad date token")


# ─────────────────────────────── API ────────────────────────────────────

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), debug: bool = Query(False)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF uploads are supported")

    # save to temp
    temp_path = "/tmp/upload.pdf"
    with open(temp_path, "wb") as fh:
        fh.write(await file.read())

    sample_lines = first_page_strings(temp_path)
    rule_name = detect_rule(sample_lines)

    if debug:
        print("FIRST-PAGE SAMPLE →", sample_lines)
        print("Detected rule:", rule_name)

    transactions = parse_pdf_to_transactions(temp_path, rule_name)
    if not transactions:
        raise HTTPException(400, "No transactions could be extracted with current rules; please verify column zones")

    # CSV output
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=transactions[0].keys())
    writer.writeheader()
    writer.writerows(transactions)

    return {
        "success": True,
        "rule": rule_name,
        "transactions": transactions,
        "csvData": buf.getvalue(),
    }
