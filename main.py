# main.py

from fastapi import FastAPI, File, UploadFile, Query, HTTPException, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import csv
import fitz  # PyMuPDF
from datetime import datetime
import re
from collections import defaultdict
import unicodedata
from rules import PARSING_RULES

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extract_lines_by_y(page):
    words = page.get_text("words")
    if not words:
        return []

    lines = defaultdict(list)
    for w in words:
        x0, y0, x1, y1, word, *_ = w
        y_key = round(y0, 1)
        lines[y_key].append((x0, word))

    ordered_lines = []
    for y in sorted(lines.keys()):
        line_words = sorted(lines[y], key=lambda x: x[0])
        line = {
            "y": y,
            "line": " ".join(word for _, word in line_words),
            "positions": [x for x, _ in line_words],
            "xmap": [(x, word) for x, word in line_words]
        }
        ordered_lines.append(line)

    return ordered_lines

def is_date(text, formats):
    for fmt in formats:
        try:
            datetime.strptime(text.replace(" ", "/").replace("-", "/"), fmt)
            return True
        except:
            continue
    return False

def normalize_amount_string(s, thousands_sep, decimal_sep, trailing_neg):
    s = unicodedata.normalize("NFKD", s)
    s = s.replace('\u00A0', '').replace('\u2009', '').replace('\u202F', '').replace(' ', '').replace(thousands_sep, '')
    s = s.replace(decimal_sep, '.')
    if trailing_neg and s.endswith("-"):
        s = '-' + s[:-1]
    return s

@app.post("/parse")
async def parse_pdf(
    preview: bool = Query(False),
    file: UploadFile = File(...)
):
    content = await file.read()

    detected_bank = None
    detected_account_type = None

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            text = page.get_text().lower()
            if "absa" in text and "cheque account statement" in text:
                detected_bank = "ABSA"
                detected_account_type = "Cheque Account Statement"
                break

    if not detected_bank or not detected_account_type:
        raise HTTPException(status_code=400, detail="Unable to detect bank/account type in PDF")

    key = f"{detected_bank.upper()}_{detected_account_type.upper().replace(' ', '_')}"
    rules = PARSING_RULES.get(key)

    if not rules:
        raise HTTPException(status_code=400, detail=f"Unsupported bank/account type configuration: {key}")

    zones = rules["column_zones"]
    thousands_sep = rules["amount_format"]["thousands_separator"]
    decimal_sep = rules["amount_format"]["decimal_separator"]
    trailing_neg = rules["amount_format"]["negative_trailing"] == "Y"
    date_formats = rules["date_format"]["formats"]
    multiline_desc = rules["description"].get("multiline", True)
    date_x_threshold = rules.get("date_x_threshold", 95)

    transactions = []
    all_lines = []

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            lines = extract_lines_by_y(page)
            all_lines.extend(lines)

    blocks = []
    current_block = []

    for line in all_lines:
        x_start = line["positions"][0] if line["positions"] else 0
        first_word = line["line"].split()[0] if line["line"].split() else ""
        if x_start < date_x_threshold and not is_date(first_word, date_formats):
            continue
        if is_date(first_word, date_formats):
            if current_block:
                blocks.append(current_block)
                current_block = []
        current_block.append(line)
    if current_block:
        blocks.append(current_block)

    previous_balance = None

    for block in blocks:
        first_line = block[0]["line"]
        match = re.match(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})", first_line)
        if not match:
            continue
        try:
            date_obj = datetime.strptime(match.group(1).replace(" ", "/").replace("-", "/"), date_formats[0])
            date = date_obj.strftime("%Y-%m-%d")
        except:
            continue

        description_parts = []
        debit_text = None
        credit_text = None
        balance_text = None

        for i, line in enumerate(block):
            for j, (x, word) in enumerate(line["xmap"]):
                if i == 0 and j == 0 and is_date(word, date_formats):
                    continue
                if zones["description"][0] <= x < zones["description"][1]:
                    description_parts.append(word)
                elif zones["debit"][0] <= x < zones["debit"][1]:
                    debit_text = word
                elif zones["credit"][0] <= x < zones["credit"][1]:
                    credit_text = word
                elif x >= zones["balance"][0]:
                    balance_text = word

        debit_amount = float(normalize_amount_string(debit_text, thousands_sep, decimal_sep, trailing_neg)) if debit_text else None
        credit_amount = float(normalize_amount_string(credit_text, thousands_sep, decimal_sep, trailing_neg)) if credit_text else None
        balance_amount = float(normalize_amount_string(balance_text, thousands_sep, decimal_sep, trailing_neg)) if balance_text else None

        description = " ".join(description_parts).strip()
        amount_val = 0.0
        if credit_amount is not None:
            amount_val = credit_amount
        elif debit_amount is not None:
            amount_val = -debit_amount

        balance_val = balance_amount if balance_amount is not None else (previous_balance if previous_balance is not None else 0.0)
        balance_diff_error = ""

        if previous_balance is not None:
            calc_amount = round(balance_val - previous_balance, 2)
            if abs(calc_amount - amount_val) > 0.01:
                balance_diff_error = f"Expected {calc_amount:.2f}, got {amount_val:.2f}"
                amount_val = calc_amount

        previous_balance = balance_val

        transactions.append({
            "date": date,
            "description": description,
            "amount": f"{amount_val:.2f}",
            "balance": f"{balance_val:.2f}",
            "calculated_balance": f"{balance_val:.2f}",
            "type": "credit" if amount_val > 0 else ("debit" if amount_val < 0 else "balance"),
            "balance_diff_error": balance_diff_error
        })

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions found in PDF")

    if preview:
        return JSONResponse(content={"preview": transactions})

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["date", "description", "amount", "balance", "calculated_balance", "type", "balance_diff_error"])
    writer.writeheader()
    for row in transactions:
        writer.writerow(row)
    output.seek(0)
    csv_string = output.getvalue()

    return JSONResponse(content={
        "success": True,
        "transactions": transactions,
        "csvData": csv_string
    })
