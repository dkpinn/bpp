# main.py

from fastapi import FastAPI, UploadFile, File, HTTPException
import io, csv, re
from typing import List, Dict, Optional

from rules import PARSING_RULES

# Try pdfminer first for keywords; fallback to fitz
try:
    from pdfminer.high_level import extract_pages  # type: ignore
    from pdfminer.layout import LTTextContainer  # type: ignore

    def _first_page_words_pdfminer(pdf_bytes: bytes) -> List[str]:
        words: List[str] = []
        for page_layout in extract_pages(io.BytesIO(pdf_bytes), maxpages=1):
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    txt = element.get_text().strip()
                    if txt:
                        words.extend(txt.split())
        return words

    _USE_PDFMINER = True
except ImportError:
    import fitz  # PyMuPDF

    def _first_page_words_pdfminer(pdf_bytes: bytes) -> List[str]:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        words = [w[4] for w in doc.load_page(0).get_text("words")]
        return words

    _USE_PDFMINER = False

import fitz  # always used for word-level extraction

def detect_account_type(sample: str) -> Optional[str]:
    s = sample.lower()
    if "absa" in s and "cheque account" in s:
        return "ABSA_CHEQUE_ACCOUNT_STATEMENT"
    if "standard bank" in s and "business current account" in s:
        return "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT"
    return None

def normalize_amount_string(raw: str, thousands_sep: str, decimal_sep: str, trailing_neg: str) -> str:
    txt = raw.strip()
    sign = ""
    if trailing_neg.upper() == "Y" and txt.endswith("-"):
        sign = "-"
        txt = txt[:-1]
    txt = txt.replace(thousands_sep, "").replace(decimal_sep, ".")
    return sign + txt

_ALPHA_RE = re.compile(r"[A-Za-z]")
_NUMERIC_CHARS_RE = re.compile(r"^[0-9.,\- ]+$")

def _looks_numeric(txt: str) -> bool:
    return bool(_NUMERIC_CHARS_RE.match(txt))

app = FastAPI()

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...)):
    pdf_bytes = await file.read()

    sample_words = _first_page_words_pdfminer(pdf_bytes)
    sample_text = " ".join(sample_words)

    rule_key = detect_account_type(sample_text)
    if not rule_key or rule_key not in PARSING_RULES:
        raise HTTPException(status_code=400, detail="Unsupported or undetected bank/account type")

    cfg = PARSING_RULES[rule_key]
    zones = cfg["column_zones"]
    fmt = cfg["amount_format"]

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    transactions: List[Dict[str, object]] = []

    for page in doc:
        words = page.get_text("words")
        line_map: Dict[tuple, List[tuple]] = {}
        for x0, y0, x1, y1, w, block_no, line_no, word_no in words:
            line_map.setdefault((block_no, line_no), []).append((x0, w))

        for parts in line_map.values():
            parts.sort(key=lambda t: t[0])
            desc, debit_raw, credit_raw, bal_raw, date_raw = [], [], [], [], []

            for x, token in parts:
                if "date" in zones and zones["date"][0] <= x <= zones["date"][1]:
                    date_raw.append(token)
                elif zones["description"][0] <= x <= zones["description"][1]:
                    desc.append(token)
                elif zones["debit"][0] <= x <= zones["debit"][1]:
                    debit_raw.append(token)
                elif zones["credit"][0] <= x <= zones["credit"][1]:
                    credit_raw.append(token)
                elif zones["balance"][0] <= x <= zones["balance"][1]:
                    bal_raw.append(token)

            amounts_concat = " ".join(debit_raw + credit_raw + bal_raw)
            if not amounts_concat or _ALPHA_RE.search(amounts_concat):
                continue

            debit_txt = "".join(debit_raw).strip()
            credit_txt = "".join(credit_raw).strip()
            bal_txt = "".join(bal_raw).strip()

            try:
                debit_val = float(normalize_amount_string(debit_txt, fmt["thousands_separator"], fmt["decimal_separator"], fmt["negative_trailing"])) if debit_txt else None
            except ValueError:
                debit_val = None
            try:
                credit_val = float(normalize_amount_string(credit_txt, fmt["thousands_separator"], fmt["decimal_separator"], fmt["negative_trailing"])) if credit_txt else None
            except ValueError:
                credit_val = None
            try:
                bal_val = float(normalize_amount_string(bal_txt, fmt["thousands_separator"], fmt["decimal_separator"], fmt["negative_trailing"])) if bal_txt else None
            except ValueError:
                bal_val = None

            txn = {
                "description": " ".join(desc).strip(),
                "debit": debit_val,
                "credit": credit_val,
                "balance": bal_val,
            }

            if date_raw:
                txn["date"] = " ".join(date_raw).strip()

            transactions.append(txn)

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions could be extracted with current rules; please verify column zones")

    # ----------------- Format output per rules.py --------------------------
    output_fields = cfg.get("output_order", ["description", "debit", "credit", "balance"])
    processed_transactions = []

    for txn in transactions:
        amount = None
        if txn.get("debit") is not None:
            amount = -txn["debit"]
        elif txn.get("credit") is not None:
            amount = txn["credit"]

        output = {
            "date": txn.get("date", ""),
            "description": txn["description"],
            "amount": amount,
            "balance": txn["balance"],
        }

        processed_transactions.append({k: output.get(k, "") for k in output_fields})

    # ----------------- Generate CSV ----------------------------------------
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=output_fields)
    writer.writeheader()
    writer.writerows(processed_transactions)

    return {
        "success": True,
        "transactions": processed_transactions,
        "csvData": buf.getvalue(),
    }
