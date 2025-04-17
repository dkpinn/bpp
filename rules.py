# rules.py

# Central place to keep parsing instructions for each supported bank / account type.
# Each entry provides:
#   • column_zones – x‑coordinate spans (in pt) for description, debit, credit, balance
#   • amount_format  – how to interpret the numbers in those columns
#   • date_format    – (kept for future use) how the date appears, should you want to parse it
#   • description.multiline – allow long descriptions to wrap (we simply join the words)
#   • date_x_threshold       – x coordinate at which we expect the date token to start
#
# Adjust / add new dicts here when new statement layouts need to be supported.

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
            "description": (0,   250),   # details column is left‑aligned
            # there is a Service‑Fee column (~255‑295) that we just ignore;
            # next come the money columns:
            "debit":       (300, 370),
            "credit":      (375, 450),
            "balance":     (455, 999),
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
