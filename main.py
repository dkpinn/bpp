from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import csv
import fitz  # PyMuPDF
from datetime import datetime
import re
from collections import defaultdict

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

# Define column zones per bank
COLUMN_ZONES = {
    "absa": {
        "description": (95, 305),
        "debit": (310, 390),
        "credit": (395, 470),
        "balance": (475, 999)
    },
    # Future banks can be added here
}

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), bank: str = Query("absa"), debug: bool = Query(False), preview: bool = Query(False)):
    content = await file.read()
    debug_lines = []
    all_lines = []
    transactions = []

    zones = COLUMN_ZONES.get(bank.lower())
    if not zones:
        raise HTTPException(status_code=400, detail=f"Unsupported bank layout: {bank}")

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page_number, page in enumerate(doc, start=1):
            lines = extract_lines_by_y(page)
            debug_lines.append(f"--- Page {page_number} ---")
            debug_lines.extend([l["line"] for l in lines])
            all_lines.extend(lines)

    blocks = []
    current_block = []
    for line in all_lines:
        x_start = line["positions"][0] if line["positions"] else 0
        first_word = line["line"].split()[0] if line["line"].split() else ""
        if x_start < 100 and not is_date(first_word):
            continue
        if is_date(first_word):
            if current_block:
                blocks.append(current_block)
                current_block = []
        current_block.append(line)
    if current_block:
        blocks.append(current_block)

    previous_balance = None

    for block in blocks:
        match = re.match(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})", block[0]["line"])
        if not match:
            continue

        date_str = match.group(1).replace(" ", "/").replace("-", "/")
        try:
            date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            continue

        description_parts = []
        debit_amount = None
        credit_amount = None
        balance_amount = None

        for i, line in enumerate(block):
            for j, (x, word) in enumerate(line["xmap"]):
                word_clean = word.replace(" ", "")
                if i == 0 and j == 0 and is_date(word):
                    continue
                if zones["description"][0] <= x < zones["description"][1] and not is_amount(word):
                    description_parts.append(word)
                elif zones["debit"][0] <= x < zones["debit"][1] and is_amount(word):
                    debit_amount = float(word_clean)
                elif zones["credit"][0] <= x < zones["credit"][1] and is_amount(word):
                    credit_amount = float(word_clean)
                elif x >= zones["balance"][0] and is_amount(word):
                    balance_amount = float(word_clean)

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
