# main.py (refined Standard Bank detection + empty‑result guard)

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

# ---------- helpers ---------- #

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
    """Return PARSING_RULES key by inspecting raw first‑page lines."""
    txt = "\n".join(first_page_lines).upper()

    # --- ABSA Cheque Statement ---
    if "CHEQUE ACCOUNT" in txt and "ABSA" in txt:
        return "ABSA_CHEQUE_ACCOUNT_STATEMENT"

    # --- Standard Bank Business Current ---
    # Require BOTH the bank name and the account‑type phrase to avoid false positives.
    if "STANDARD BANK" in txt and "BUSINESS CURRENT ACCOUNT" in txt:
        return "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT"

    return None

# ---------- amount utils ---------- #

def normalize_amount_string(text, thous, dec, trailing_neg):
    text = text.strip()
    if trailing_neg.upper() == "Y" and text.endswith("-"):
        text = "-" + text[:-1]
    if thous:
        text = text.replace(thous, "")
    if dec and dec != ".":
        text = text.replace(dec, ".")
    # remove any commas that might sneak into CSV fields
    return text.replace(",", "")


def safe_parse_amount(text, thous, dec, trailing_neg):
    if not text:
        return None
    try:
        return float(normalize_amount_string(text, thous, dec, trailing_neg))
    except ValueError:
        return None

# ---------- API ---------- #

@app.post("/parse")
async def parse_pdf(
    file: UploadFile = File(...),
    debug: bool = Query(False)
):
    content = await file.read()

    with fitz.open(stream=content, filetype="pdf") as doc:
        first_lines = extract_lines_by_y(doc[0])
        first_page_lines = [l["line"] for l in first_lines]
        if debug:
            print("FIRST‑PAGE SAMPLE →", first_page_lines[:50])

        doc_key = detect_bank_account_type(first_page_lines)
        if not doc_key or doc_key not in PARSING_RULES:
            raise HTTPException(status_code=400, detail="Unsupported or undetected bank/account type")
        rules = PARSING_RULES[doc_key]

        # column ranges
        desc_min, desc_max = rules["column_zones"]["description"]
        debit_min, debit_max = rules["column_zones"]["debit"]
        credit_min, credit_max = rules["column_zones"]["credit"]
        bal_min = rules["column_zones"]["balance"][0]

        thous = rules["amount_format"].get("thousands_separator", "")
        dec = rules["amount_format"].get("decimal_separator", ".")
        trailing_neg = rules["amount_format"].get("negative_trailing", "N")

        date_threshold = rules["date_x_threshold"]
        date_formats = rules["date_format"]["formats"]
        year_optional = rules["date_format"].get("year_optional", "N") == "Y"

        # -------- extract every line of every page -------- #
        all_lines = []
        for page in doc:
            all_lines.extend(extract_lines_by_y(page))

    # -------- group into blocks (transaction rows) -------- #
    blocks, cur = [], []
    for line in all_lines:
        if line["positions"] and line["positions"][0] <= date_threshold and cur:
            blocks.append(cur)
            cur = []
        cur.append(line)
    if cur:
        blocks.append(cur)

    # -------- parse each block -------- #
    transactions, prev_bal = [], None
    for blk in blocks:
        # grab date token
        date_token = next((w for x, w in blk[0]["xmap"] if x <= date_threshold), None)
        if not date_token:
            continue
        date_str = None
        for fmt in date_formats:
            try:
                token = date_token
                if year_optional and len(token.split()) == 2:
                    token += f" {datetime.now().year}"
                date_str = datetime.strptime(token, fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        if not date_str:
            continue

        desc_parts, debit_txt, credit_txt, bal_txt = [], None, None, None
        for ln in blk:
            for x, w in ln["xmap"]:
                if desc_min <= x < desc_max:
                    desc_parts.append(w)
                elif debit_min <= x < debit_max:
                    debit_txt = (debit_txt or "") + w
                elif credit_min <= x < credit_max:
                    credit_txt = (credit_txt or "") + w
                elif x >= bal_min:
                    bal_txt = (bal_txt or "") + w

        amount = 0.0
        debit_val = safe_parse_amount(debit_txt, thous, dec, trailing_neg)
        credit_val = safe_parse_amount(credit_txt, thous, dec, trailing_neg)
        balance_val = safe_parse_amount(bal_txt, thous, dec, trailing_neg) or prev_bal or 0.0

        if debit_val is not None and credit_val is None:
            amount = -debit_val
        elif credit_val is not None and debit_val is None:
            amount = credit_val

        prev_bal = balance_val
        transactions.append({
            "date": date_str,
            "description": " ".join(desc_parts).strip(),
            "amount": f"{amount:.2f}",
            "balance": f"{balance_val:.2f}",
            "type": "credit" if amount > 0 else ("debit" if amount < 0 else "balance")
        })

    # ---- guard: no rows ---- #
    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions could be extracted with current rules; please verify column zones")

    # ---- CSV ---- #
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=transactions[0].keys())
    writer.writeheader()
    writer.writerows(transactions)
    buf.seek(0)

    return JSONResponse({"success": True, "transactions": transactions, "csvData": buf.getvalue()})
