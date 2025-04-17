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

def is_valid_amount(text):
    return re.search(r"\d", text)

def normalize_amount_string(text, thousands_sep, decimal_sep, trailing_neg):
    cleaned = text.replace(thousands_sep, "").replace(decimal_sep, ".").strip()
    if trailing_neg == "Y" and cleaned.endswith("-"):
        cleaned = "-" + cleaned[:-1]
    return cleaned

def safe_parse_amount(text, thousands_sep, decimal_sep, trailing_neg):
    if not text or not is_valid_amount(text):
        return None
    try:
        normalized = normalize_amount_string(text, thousands_sep, decimal_sep, trailing_neg)
        return float(normalized)
    except ValueError:
        return None

def detect_bank_account_type(lines):
    for line in lines:
        content = line["line"].lower()
        if "absa" in content and "cheque account" in content:
            return "ABSA_CHEQUE_ACCOUNT_STATEMENT"
        if "standard bank" in content and "business current account" in content:
            return "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT"
    return None

@app.post("/parse")
async def parse_pdf(file: UploadFile = File(...), debug: bool = Query(False)):
    content = await file.read()
    with fitz.open(stream=content, filetype="pdf") as doc:
        first_page_lines = extract_lines_by_y(doc[0])
        account_type = detect_bank_account_type(first_page_lines)
        if not account_type or account_type not in PARSING_RULES:
            raise HTTPException(status_code=400, detail="Unsupported or undetected bank/account type")

        rules = PARSING_RULES[account_type]
        zones = rules["column_zones"]
        transactions = []
        debug_log = []

        for page in doc:
            lines = extract_lines_by_y(page)
            current_block = []

            for line in lines:
                line_text = line["line"]
                date_candidate = next((word for x, word in line["xmap"] if x < rules["date_x_threshold"] and re.match(r"\d{1,2}[ /-]\d{1,2}([ /-]\d{2,4})?", word)), None)
                if date_candidate:
                    if current_block:
                        transactions.append(current_block)
                        current_block = []
                current_block.append(line)
            if current_block:
                transactions.append(current_block)

        output_data = []
        previous_balance = None
        for block in transactions:
            date_str = next((word for x, word in block[0]["xmap"] if x < rules["date_x_threshold"] and re.match(r"\d{1,2}[ /-]\d{1,2}([ /-]\d{2,4})?", word)), None)
            date_fmt = rules["date_format"]["formats"][0]
            year_optional = rules["date_format"]["year_optional"] == "Y"

            if not date_str:
                continue

            if year_optional and len(date_str.split()[-1]) != 4:
                date_str += " 2025"

            try:
                date_obj = datetime.strptime(date_str, date_fmt)
                date = date_obj.strftime("%Y-%m-%d")
            except:
                continue

            description_parts = []
            debit_text = ""
            credit_text = ""
            balance_text = ""

            for line in block:
                skip_line = False
                for x, word in line["xmap"]:
                    if zones["debit"][0] <= x < zones["balance"][1] and re.search(r"[a-zA-Z]", word):
                        skip_line = True
                        break
                if skip_line:
                    continue

                for x, word in line["xmap"]:
                    if zones["description"][0] <= x < zones["description"][1]:
                        description_parts.append(word)
                    elif zones["debit"][0] <= x < zones["debit"][1]:
                        debit_text += word
                    elif zones["credit"][0] <= x < zones["credit"][1]:
                        credit_text += word
                    elif zones["balance"][0] <= x < zones["balance"][1]:
                        balance_text += word

            debit_amount = safe_parse_amount(debit_text, **rules["amount_format"])
            credit_amount = safe_parse_amount(credit_text, **rules["amount_format"])
            balance_amount = safe_parse_amount(balance_text, **rules["amount_format"])

            description = " ".join(description_parts).strip()
            amount_val = 0.0
            if credit_amount is not None:
                amount_val = credit_amount
            elif debit_amount is not None:
                amount_val = -debit_amount

            balance_val = balance_amount if balance_amount is not None else (previous_balance or 0.0)
            previous_balance = balance_val

            tx_type = "credit" if amount_val > 0 else ("debit" if amount_val < 0 else "balance")
            if tx_type == "balance":
                continue  # Skip pure balance entries

            output_data.append({
                "date": date,
                "description": description,
                "amount": f"{amount_val:.2f}",
                "balance": f"{balance_val:.2f}",
                "type": tx_type
            })

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["date", "description", "amount", "balance", "type"])
        writer.writeheader()
        for row in output_data:
            writer.writerow(row)
        output.seek(0)

        return JSONResponse(content={
            "success": True,
            "transactions": output_data,
            "csvData": output.getvalue()
        })
