from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
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
            "positions": [x for x, _ in line_words]
        }
        ordered_lines.append(line)

    return ordered_lines

def is_transaction_line(text_line):
    return re.match(r"^\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4}", text_line)

def extract_fields(line, inferred_year):
    def clean(n):
        return n.replace(",", "").replace(" ", "")

    patterns = [
        re.compile(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})\s+(.*?)\s+([\d\s]+\.?\d{2})\s+([\d\s]+\.?\d{2})$"),
        re.compile(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})\s+(.*?)\s+([\d\s]+\.?\d{2})$")
    ]

    for pattern in patterns:
        match = pattern.match(line)
        if match:
            parts = match.groups()
            date_str = parts[0].strip()
            try:
                date = datetime.strptime(date_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                date = date_str
            desc = parts[1].strip()
            amount = clean(parts[2]) if len(parts) > 2 else ""
            balance = clean(parts[3]) if len(parts) > 3 else ""
            return {
                "date": date,
                "description": desc,
                "amount": amount,
                "balance": balance
            }
    return None

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), debug: bool = Query(False), preview: bool = Query(False)):
    content = await file.read()
    transactions = []
    inferred_year = datetime.today().year
    debug_lines = []

    with fitz.open(stream=content, filetype="pdf") as doc:
        current_transaction = None
        previous_balance = None

        for page_number, page in enumerate(doc, start=1):
            lines = extract_lines_by_y(page)
            if not lines:
                continue
            debug_lines.append(f"--- Page {page_number} ---")
            debug_lines.extend([l["line"] for l in lines])
            for line_obj in lines:
                line = line_obj["line"]
                if "Balance Brought Forward" in line:
                    match = re.search(r"Balance Brought Forward\s+([\d.,\s]+)", line)
                    if match:
                        previous_balance = float(match.group(1).replace(",", "").replace(" ", ""))

                if is_transaction_line(line):
                    if current_transaction:
                        transactions.append(current_transaction)
                    fields = extract_fields(line, inferred_year)
                    if fields:
                        current_transaction = fields
                else:
                    if current_transaction:
                        current_transaction['description'] += ' ' + line.strip()
            if current_transaction:
                transactions.append(current_transaction)

    if debug:
        return PlainTextResponse("\n".join(debug_lines), media_type="text/plain")

    if not transactions:
        raise HTTPException(status_code=400, detail="No transactions found in PDF")

    calculated_transactions = []
    running_balance = previous_balance

    for row in transactions:
        amount = float(row['amount']) if row['amount'] else 0.0
        official_balance = float(row['balance']) if row['balance'] else ""

        if running_balance is not None:
            diff = round(official_balance - running_balance, 2) if row['balance'] else amount
            signed_amount = diff
            calculated_balance = round(running_balance + signed_amount, 2)
            running_balance = calculated_balance
        else:
            signed_amount = amount
            calculated_balance = ""

        calculated_transactions.append({
            "date": row['date'],
            "description": row['description'],
            "amount": f"{signed_amount:.2f}",
            "balance": row['balance'],
            "calculated_balance": f"{calculated_balance:.2f}" if calculated_balance != "" else ""
        })

    if preview:
        return JSONResponse(content={"preview": calculated_transactions})

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["date", "description", "amount", "balance", "calculated_balance"])
    writer.writeheader()
    for row in calculated_transactions:
        writer.writerow(row)
    output.seek(0)
    csv_string = output.getvalue()

    return JSONResponse(content={
        "success": True,
        "transactions": calculated_transactions,
        "csvData": csv_string
    })
