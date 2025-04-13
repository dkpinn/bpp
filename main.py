from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import csv
import fitz  # PyMuPDF
from datetime import datetime
import re
from collections import defaultdict, Counter

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

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), debug: bool = Query(False), preview: bool = Query(False)):
    content = await file.read()
    debug_lines = []
    all_lines = []
    transactions = []

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
        full_text = " ".join([line["line"] for line in block])
        match = re.match(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})", block[0]["line"])
        if not match:
            continue

        date_str = match.group(1).replace(" ", "/").replace("-", "/")
        try:
            date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
        except:
            continue

        description_parts = []
        for line in block:
            left_column_words = [word for x, word in line["xmap"] if x < 300 and not is_amount(word)]
            description_parts.append(" ".join(left_column_words))

        cleaned_description = " ".join(description_parts).strip()

        numbers = re.findall(r"[\d\s]+\.\d{2}", full_text)
        amount = ""
        balance = ""
        balance_diff_error = ""

        if len(numbers) == 1:
            balance = numbers[0]
            amount = "0.00"
        elif len(numbers) >= 2:
            amount = numbers[-2]
            balance = numbers[-1]

        try:
            amount_val = float(amount.replace(" ", "")) if amount else 0.0
        except:
            amount_val = 0.0

        try:
            balance_val = float(balance.replace(" ", "")) if balance else 0.0
        except:
            balance_val = 0.0

        if previous_balance is not None:
            calc_amount = round(balance_val - previous_balance, 2)
            if abs(calc_amount - amount_val) > 0.01:
                balance_diff_error = f"Expected {calc_amount:.2f}, got {amount_val:.2f}"
                amount_val = calc_amount

        previous_balance = balance_val

        transactions.append({
            "date": date,
            "description": cleaned_description,
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
