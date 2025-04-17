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
    # Standard Bank – Business Current Account (re‑tuned 2025‑04‑18)
    # ---------------------------------------------------------------------
    "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT": {
        "column_zones": {
            # The statement squeezes everything toward the centre – give the
            # description plenty of room so multi‑line text stays together.
            "description": (0,   330),   # widened
            "debit":       (335, 410),   # left‑aligned numbers with trailing “‑”
            "credit":      (415, 495),   # credits (black text)
            "balance":     (500, 999),   # running balance (right‑aligned)
        },
        "amount_format": {
            "thousands_separator": ".",  # e.g. 125.000,00
            "decimal_separator":   ",",
            "negative_trailing":   "Y",   # minus sign appears *after* the amount
        },
        "date_format": {
            # Dates are printed as two two‑digit tokens: "03 22" → 22 March (we assume
            # the year from the statement period). We’ll parse “%m %d”.
            "formats": ["%m %d"],
            "year_optional": "Y",
        },
        "description": {
            "multiline": True,
        },
        # Any x‑coordinate to the right of this is definitely *not* a date – this
        # helps us ignore the balance column when scanning for the day/month pair.
        "date_x_threshold": 440,
    },
}
