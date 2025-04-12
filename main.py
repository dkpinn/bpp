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

def is_transaction_line(text_line):
    return re.match(r"^\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4}", text_line)

def classify_amounts_by_position(lines):
    amount_positions = []
    for line in lines:
        numbers = [(x, w) for x, w in line["xmap"] if re.match(r"^[\d\s]+\.\d{2}$", w)]
        for x, word in numbers:
            amount_positions.append(round(x))
    most_common = Counter(amount_positions).most_common()
    zones = sorted(set(x for x, _ in most_common))
    return zones[:3]  # Assume 3 zones: debit, credit, balance

def extract_using_positions(line_obj, zones):
    numbers = [(x, w) for x, w in line_obj["xmap"] if re.match(r"^[\d\s]+\.\d{2}$", w)]
    values = sorted([(abs(x - z), z, x, w) for x, w in numbers for z in zones])
    seen = set()
    fields = {}
    for _, z, x, w in values:
        if z in seen:
            continue
        seen.add(z)
        clean_val = w.replace(" ", "").replace(",", "")
        if "debit" not in fields:
            fields["debit"] = clean_val
        elif "credit" not in fields:
            fields["credit"] = clean_val
        elif "balance" not in fields:
            fields["balance"] = clean_val
    return fields

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), debug: bool = Query(False), preview: bool = Query(False)):
    content = await file.read()
    inferred_year = datetime.today().year
    debug_lines = []
    all_lines = []
    transactions = []

    with fitz.open(stream=content, filetype="pdf") as doc:
        for page_number, page in enumerate(doc, start=1):
            lines = extract_lines_by_y(page)
            debug_lines.append(f"--- Page {page_number} ---")
            debug_lines.extend([l["line"] for l in lines])
            all_lines.extend(lines)

    zones = classify_amounts_by_position(all_lines)
    debug_lines.append(f"Detected zones (X-coordinates): {zones}")
    zone_info = {str(z): 0 for z in zones}

    current_transaction = None
    previous_balance = None
    for line_obj in all_lines:
        line = line_obj["line"]
        if "Balance Brought Forward" in line:
            match = re.search(r"Balance Brought Forward\s+([\d.,\s]+)", line)
            if match:
                previous_balance = float(match.group(1).replace(",", "").replace(" ", ""))

        if is_transaction_line(line):
            if current_transaction:
                transactions.append(current_transaction)
            date_match = re.match(r"^(\d{1,2}[\/\-\s]\d{1,2}[\/\-\s]\d{2,4})", line)
            date = date_match.group(1) if date_match else ""
            try:
                date = datetime.strptime(date, "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                pass
            desc = line[len(date):].strip() if date else line.strip()
            fields = extract_using_positions(line_obj, zones)
            amount = fields.get("debit") or fields.get("credit") or ""
            current_transaction = {
                "date": date,
                "description": desc,
                "amount": amount,
                "balance": fields.get("balance", "")
            }
        else:
            if current_transaction:
                current_transaction["description"] += " " + line.strip()

    if current_transaction:
        transactions.append(current_transaction)

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

        type_label = "credit" if signed_amount > 0 else ("debit" if signed_amount < 0 else "balance")

        x_pos = None
        for line in all_lines:
            if row['description'].split()[0] in line['line']:
                for x, w in line['xmap']:
                    if row['amount'].replace('.', '') in w.replace('.', ''):
                        x_pos = round(x)
                        break
                break
        zone_match = min(zones, key=lambda z: abs(z - x_pos)) if x_pos is not None else None
        if zone_match is not None:
            zone_info[str(zone_match)] += 1

        calculated_transactions.append({
            "date": row['date'],
            "description": row['description'],
            "amount": f"{signed_amount:.2f}",
            "balance": row['balance'],
            "calculated_balance": f"{calculated_balance:.2f}" if calculated_balance != "" else "",
            "type": type_label
        })

    if preview:
        return JSONResponse(content={
            "preview": calculated_transactions,
            "zones": zones,
            "zone_match_distribution": zone_info
        })

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["date", "description", "amount", "balance", "calculated_balance", "type"])
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
