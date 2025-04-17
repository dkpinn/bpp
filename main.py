# main.py (debug version with improved first‑page detection)

from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io, csv, fitz, re
from datetime import datetime
from collections import defaultdict

from rules import PARSING_RULES

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- small helpers ---------- #

def extract_lines_by_y(page):
    words = page.get_text("words")
    if not words:
        return []
    lines = defaultdict(list)
    for w in words:
        x0, y0, x1, y1, word, *_ = w
        y_key = round(y0, 1)
        lines[y_key].append((x0, word))
    ordered = []
    for y in sorted(lines):
        line_words = sorted(lines[y], key=lambda t: t[0])
        ordered.append({
            "y": y,
            "line": " ".join(w for _, w in line_words),
            "positions": [x for x, _ in line_words],
            "xmap": line_words,
        })
    return ordered


def detect_bank_account_type(first_page_lines):
    """Return the parsing‑rule key given the raw lines of the first page."""
    txt = "\n".join(first_page_lines).upper()

    # ABSA cheque
    if "CHEQUE ACCOUNT" in txt and "ABSA" in txt:
        return "ABSA_CHEQUE_ACCOUNT_STATEMENT"

    # Standard Bank business current (look for either full name or common "STANDARD BANK" substring)
    if "BUSINESS CURRENT ACCOUNT" in txt and ("STANDARD BANK" in txt or "THE STANDARD BANK" in txt):
        return "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT"

    return None

# ---------- amount utils ---------- #

def normalize_amount_string(text, thous, dec, trailing_neg):
    # strip spaces/newlines
    text = text.strip()
    # handle trailing negative sign
    if trailing_neg.upper() == "Y" and text.endswith("-"):
        text = "-" + text[:-1]
    # remove thousands separator & replace decimal separator with '.'
    if thous:
        text = text.replace(thous, "")
    if dec and dec != ".":
        text = text.replace(dec, ".")
    # any stray commas left (CSV guard)
    text = text.replace(",", "")
    return text


def safe_parse_amount(text, thous, dec, trailing_neg):
    if not text:
        return None
    try:
        return float(normalize_amount_string(text, thous, dec, trailing_neg))
    except ValueError:
        return None

# ---------- main endpoint ---------- #

@app.post("/parse")
async def parse_pdf(
    file: UploadFile = File(...),
    debug: bool = Query(False)
):
    content = await file.read()
    transactions = []

    with fitz.open(stream=content, filetype="pdf") as doc:
        # --- read first page to auto‑detect rule set ---
        first_page = doc[0]
        first_lines = extract_lines_by_y(first_page)
        first_page_lines = [l["line"] for l in first_lines]  # **no slicing ‑ use full page**
        print("FIRST PAGE LINES FOR DETECTION →", first_page_lines[:100])  # print first 100 for brevity

        doc_key = detect_bank_account_type(first_page_lines)
        if not doc_key or doc_key not in PARSING_RULES:
            raise HTTPException(status_code=400, detail="Unsupported or undetected bank/account type")
        rules = PARSING_RULES[doc_key]

        desc_min, desc_max = rules["column_zones"]["description"]
        debit_min, debit_max = rules["column_zones"]["debit"]
        credit_min, credit_max = rules["column_zones"]["credit"]
        bal_min = rules["column_zones"]["balance"][0]

        thous = rules["amount_format"]["thousands_separator"]
        dec = rules["amount_format"]["decimal_separator"]
        trailing_neg = rules["amount_format"]["negative_trailing"]

        date_threshold = rules["date_x_threshold"]
        date_formats = rules["date_format"]["formats"]
        year_optional = rules["date_format"]["year_optional"] == "Y"

        all_lines = []
        for page in doc:
            all_lines.extend(extract_lines_by_y(page))

    # --- build blocks per transaction ---
    blocks, cur_block = [], []
    for line in all_lines:
        x_start = line["positions"][0] if line["positions"] else 0
        if x_start <= date_threshold:
            if cur_block:
                blocks.append(cur_block)
                cur_block = []
        cur_block.append(line)
    if cur_block:
        blocks.append(cur_block)

    prev_balance = None
    for block in blocks:
        words_pos = block[0]["xmap"]
        date_tok = None
        for x, w in words_pos:
            if x <= date_threshold:
                date_tok = w
                break
        if date_tok is None:
            continue

        dt = None
        for fmt in date_formats:
            try:
                if year_optional and len(date_tok.split()) == 2:
                    date_tok_full = f"{date_tok} {datetime.now().year}"
                else:
                    date_tok_full = date_tok
                dt = datetime.strptime(date_tok_full, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        if dt is None:
            continue

        desc_parts, debit_txt, credit_txt, bal_txt = [], None, None, None
        for line in block:
            for x, w in line["xmap"]:
                if desc_min <= x < desc_max:
                    desc_parts.append(w)
                elif debit_min <= x < debit_max:
                    debit_txt = (debit_txt or "") + w
                elif credit_min <= x < credit_max:
                    credit_txt = (credit_txt or "") + w
                elif x >= bal_min:
                    bal_txt = (bal_txt or "") + w
        desc = " ".join(desc_parts).strip()
        debit_val = safe_parse_amount(debit_txt, thous, dec, trailing_neg)
        credit_val = safe_parse_amount(credit_txt, thous, dec, trailing_neg)
        balance_val = safe_parse_amount(bal_txt, thous, dec, trailing_neg) or prev_balance or 0.0

        if debit_val is not None and credit_val is None:
            amount = -debit_val
        elif credit_val is not None and debit_val is None:
            amount = credit_val
        else:
            amount = 0.0

        prev_balance = balance_val
        transactions.append({
            "date": dt,
            "description": desc,
            "amount": f"{amount:.2f}",
            "balance": f"{balance_val:.2f}",
            "type": "credit" if amount > 0 else ("debit" if amount < 0 else "balance")
        })

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=transactions[0].keys())
    writer.writeheader()
    writer.writerows(transactions)
    buf.seek(0)
    return JSONResponse({"success": True, "transactions": transactions, "csvData": buf.getvalue()})
