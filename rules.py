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
"""

PARSING_RULES = {
    # ---------------------------------------------------------------------
    # ABSA – Cheque Account (the one we had working earlier)
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
    # Standard Bank – Business Current Account
    # ---------------------------------------------------------------------
    "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT": {
        "column_zones": {
            "description":  (0,   250),   # main details on the left
            "service_fee":  (255, 305),   # Service‑Fee column (ignored for amounts)
            "debit":        (305, 363),   # purple – amounts incl. trailing "‑"
            "credit":       (363, 400),   # yellow  – credits, right up to next grey bar
            "month_year":   (400, 465),   # *new* orange band – "03 22", etc.
            "balance":      (470, 999),   # pink – running balance
        },
        "amount_format": {
            "thousands_separator": ".",  # e.g. 125.000,00
            "decimal_separator":   ",",
            "negative_trailing":   "Y",  # negative sign appears at the *end*, e.g. 800,00‑
        },
        "date_format": {
            "formats": ["%m %d"],   # appears as "03 22" etc.
            "year_optional": "Y",   # we will fill in year from header if needed
        },
        "description": {
            "multiline": True,
        },
        "date_x_threshold": 600,  # date is far right on these statements
    },
}
