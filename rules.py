# rules.py

"""Central place to keep parsing instructions for each supported bank / account type.

Each entry provides:
    • column_zones – x‑coordinate spans (in pt) for description, debit, credit, balance (and any extras)
    • amount_format  – how to interpret the numbers in those columns
    • date_format    – (kept for future use) how the date appears, should you want to parse it
    • description.multiline – allow long descriptions to wrap (we simply join the words)
    • date_x_threshold       – x coordinate at which we expect the date token to start

Update 2025‑04‑17
-----------------
• **STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT**
  – added an explicit *service_fee* column and a *month_year* column.
  – tweaked the other x‑coordinate spans per latest visual feedback.

Update 2025‑04‑18
-----------------
• **STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT (tweak)**
  – dramatically widened *description* zone and nudged the numeric columns rightwards.
  – dropped the dedicated *service_fee* column (turns out the fee amount prints in the debit column).
  – lowered *date_x_threshold* so we do not mistakenly treat numbers that belong to the balance column as dates.
  – verified the *negative_trailing* logic – trailing "‑" is preserved.

Update 2025‑04‑19
-----------------
• **STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT (major realign)**
  – credit/debit values were still being polluted by the day‑of‑month token (the stray 22.0 / 23.0 / … you saw).
    Root cause: the credit / debit columns started too far left, overlapping the date pair.
  – **Fix**: pushed all numeric columns ~130 pt to the right and let *description* own pretty much the whole
    left half of the page.  Date detection is now gated by `date_x_threshold = 120`.
  – sanity‑tested on the same statement: description text is populated, credit/debit/balance amounts land in
    the correct buckets, no 22.0 ghosts.
"""

PARSING_RULES = {
    # ---------------------------------------------------------------------
    # ABSA – Cheque Account (unchanged)
    # ---------------------------------------------------------------------
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {
        "column_zones": {
            "description": (95, 305),
            "debit":       (310, 390),
            "credit":      (395, 470),
            "balance":     (475, 999),
        },
        "amount_format": {
            "thousands_separator": " ",   # space
            "decimal_separator":   ".",
            "negative_trailing":   "N",  # values are printed with leading minus (‑123.45)
        },
        "date_format": {
            "formats":       ["%d/%m/%Y"],
            "year_optional": "N",
        },
        "description": {
            "multiline": True,
        },
        "date_x_threshold": 95,
    },

    # ---------------------------------------------------------------------
    # Standard Bank – Business Current Account (re‑tuned 2025‑04‑19)
    # ---------------------------------------------------------------------
    "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT": {
        "column_zones": {
            # Give the description *all* the left‑hand real‑estate –
            # this keeps wrapped text intact and isolates the date pair.
            "description": (0,   460),    # widened even more
            # numeric columns slid ~130 pt to the right compared to 2025‑04‑18
            "debit":       (465, 540),
            "credit":      (545, 630),
            "balance":     (635, 999),
        },
        "amount_format": {
            "thousands_separator": ".",   # e.g. 125.000,00
            "decimal_separator":   ",",
            "negative_trailing":   "Y",    # minus sign appears *after* the amount
        },
        "date_format": {
            # Dates are printed as two tokens: "03 22" → 22 March.
            "formats": ["%m %d"],
            "year_optional": "Y",
        },
        "description": {
            "multiline": True,
        },
        # Anything past 120 pt definitely isn't a date – ensures we ignore the debit/credit/balance columns.
        "date_x_threshold": 120,
    },
}
