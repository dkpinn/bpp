from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import csv
import fitz  # PyMuPDF
from datetime import datetime
import re
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

def normalize_amount(text, sep, trail_neg):
    num = text.replace(sep, '').replace(',', '').strip()
    if trail_neg == "Y" and num.endswith("-"):
        num = "-" + num[:-1]
    return float(num)

def match_date(text, formats):
    for fmt in formats:
        try:
            return datetime.strptime(text.replace(" ", "/"), fmt).strftime("%Y-%m-%d")
        except:
            continue
    return None

@app.post("/parse")
async def parse_pdf(
    file: UploadFile = File(...), 
    bank: str = Query("ABSA"), 
    account_type: str = Query("CHEQUE_ACCOUNT_STATEMENT"), 
    preview: bool = Query(False)):

    key = f"{bank.upper()}_{account_type.upper()}"
    rules = PARSING_RULES.get(key)
    if not rules:
        raise HTTPException(status_code=400, detail=f"Unsupported bank/account type configuration: {key}")

    content = await file.read()
    transactions = []
    all_lines = []

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page in doc:
            lines = extract_lines_by_y(page)
            all_lines.extend(lines)

    column_zones = rules["column_zones"]
    prev_balance = None
    current_block = []
    blocks = []

    for line in all_lines:
        x_start = line["positions"][0] if line["positions"] else 0
        first_word = line["line"].split()[0] if line["line"].split() else ""
        if x_start < rules["date_x_threshold"] and not re.match(r"\d{1,2}[\-/\s]\d{1,2}([\-/\s]\d{2,4})?", first_word):
            continue
        if re.match(r"\d{1,2}[\-/\s]\d{1,2}([\-/\s]\d{2,4})?", first_word):
            if current_block:
                blocks.append(current_block)
                current_block = []
        current_block.append(line)
    if current_block:
        blocks.append(current_block)

    for block in blocks:
        date_str = match_date(block[0]["line"].split()[0], rules["date_format"]["formats"])
        if not date_str:
            continue

        desc_parts = []
        debit, credit, balance = None, None, None

        for i, line in enumerate(block):
            for x, word in line["xmap"]:
                clean = word.replace(" ", "").replace(",", "")
                if i == 0 and re.match(r"\d{1,2}[\-/\s]\d{1,2}([\-/\s]\d{2,4})?", word):
                    continue
                if column_zones["description"][0] <= x < column_zones["description"][1] and not re.match(r"^[\d\s]+\.\d{2}$", word):
                    desc_parts.append(word)
                elif column_zones["debit"][0] <= x < column_zones["debit"][1] and re.match(r"^[\d\s\-,]+\.\d{2}-?", word):
                    debit = normalize_amount(word, rules["amount_format"]["thousands_separator"], rules["amount_format"]["negative_trailing"])
                elif column_zones["credit"][0] <= x < column_zones["credit"][1] and re.match(r"^[\d\s\-,]+\.\d{2}-?", word):
                    credit = normalize_amount(word, rules["amount_format"]["thousands_separator"], rules["amount_format"]["negative_trailing"])
                elif x >= column_zones["balance"][0] and re.match(r"^[\d\s\-,]+\.\d{2}-?", word):
                    balance = normalize_amount(word, rules["amount_format"]["thousands_separator"], rules["amount_format"]["negative_trailing"])

        description = " ".join(desc_parts).strip()
        amount = credit if credit is not None else (-debit if debit is not None else 0.0)
        bal_val = balance if balance is not None else (prev_balance if prev_balance is not None else 0.0)

        error = ""
        if prev_balance is not None:
            expected_amt = round(bal_val - prev_balance, 2)
            if abs(expected_amt - amount) > 0.01:
                error = f"Expected {expected_amt:.2f}, got {amount:.2f}"
                amount = expected_amt

        prev_balance = bal_val

        transactions.append({
            "date": date_str,
            "description": description,
            "amount": f"{amount:.2f}",
            "balance": f"{bal_val:.2f}",
            "calculated_balance": f"{bal_val:.2f}",
            "type": "credit" if amount > 0 else ("debit" if amount < 0 else "balance"),
            "balance_diff_error": error
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

    return JSONResponse(content={
        "success": True,
        "transactions": transactions,
        "csvData": output.getvalue()
    })
