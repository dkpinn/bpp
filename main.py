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

def is_date(text):
    return re.match(r"^\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4}$", text)

def is_amount(text):
    return re.match(r"^[\d\s]+\.\d{2}$", text)

def clean_description(desc, amount_candidates):
    for a in amount_candidates:
        if a in desc:
            desc = desc.replace(a, "")
    return re.sub(r"\s+", " ", desc).strip()

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), bank: str = Query("ABSA"), account_type: str = Query("CHEQUE_ACCOUNT_STATEMENT"), preview: bool = Query(False)):
    key = f"{bank.upper()}_{account_type.upper()}"
    rules = PARSING_RULES.get(key)
    if not rules:
        raise HTTPException(status_code=400, detail=f"Unsupported bank/account type configuration: {key}")

    content = await file.read()
    with fitz.open(stream=content, filetype="pdf") as doc:
        all_lines = []
        for page in doc:
            all_lines.extend(extract_lines_by_y(page))

    blocks = []
    current_block = []
    for line in all_lines:
        x_start = line["positions"][0] if line["positions"] else 0
        first_word = line["line"].split()[0] if line["line"].split() else ""
        if x_start < rules["date_x_threshold"] and not is_date(first_word):
            continue
        if is_date(first_word):
            if current_block:
                blocks.append(current_block)
                current_block = []
        current_block.append(line)
    if current_block:
        blocks.append(current_block)

    transactions = []
    previous_balance = None
    zones = rules["column_zones"]

    for block in blocks:
        match = re.match(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})", block[0]["line"])
        if not match:
            continue

        date_str = match.group(1).replace(" ", "/").replace("-", "/")
        try:
            date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            continue

        desc_parts, debit, credit, balance = [], None, None, None
        for i, line in enumerate(block):
            for j, (x, word) in enumerate(line["xmap"]):
                word_clean = word.replace(" ", "")
                if i == 0 and j == 0 and is_date(word):
                    continue
                if zones["description"][0] <= x < zones["description"][1] and not is_amount(word):
                    desc_parts.append(word)
                elif zones["debit"][0] <= x < zones["debit"][1] and is_amount(word):
                    debit = float(word_clean.replace(",", "").replace(" ", ""))
                elif zones["credit"][0] <= x < zones["credit"][1] and is_amount(word):
                    credit = float(word_clean.replace(",", "").replace(" ", ""))
                elif x >= zones["balance"][0] and is_amount(word):
                    balance = float(word_clean.replace(",", "").replace(" ", ""))

        desc = " ".join(desc_parts).strip()
        raw_amounts = re.findall(r"\d[\d\s]*\.\d{2}-?", desc)
        desc = clean_description(desc, raw_amounts)

        amount_val = 0.0
        if credit is not None:
            amount_val = credit
        elif debit is not None:
            amount_val = -debit

        balance_val = balance if balance is not None else (previous_balance if previous_balance is not None else 0.0)
        balance_diff_error = ""
        if previous_balance is not None:
            calc_amount = round(balance_val - previous_balance, 2)
            if abs(calc_amount - amount_val) > 0.01:
                balance_diff_error = f"Expected {calc_amount:.2f}, got {amount_val:.2f}"
                amount_val = calc_amount
        previous_balance = balance_val

        transactions.append({
            "date": date,
            "description": desc,
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

    return JSONResponse(content={
        "success": True,
        "transactions": transactions,
        "csvData": output.getvalue()
    })
