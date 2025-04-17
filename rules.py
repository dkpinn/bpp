# --- rules.py ---------------------------------------------------------------
PARSING_RULES = {
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {   # <-- unchanged
        "column_zones": {
            "description": (95, 305),
            "debit":       (310, 390),
            "credit":      (395, 470),
            "balance":     (475, 999),
        },
        "amount_format": {
            "thousands_separator": " ",
            "decimal_separator":  ".",
            "negative_trailing":  "N",
        },
        "date_format": {
            "formats": ["%d/%m/%Y"],
            "year_optional": "N",
        },
        "description": {"multiline": True},
        "date_x_threshold": 95,
    },

    # ------------------------------------------------------------------ #
    # NEW: Standard Bank  – Business Current Account (PDF “Details / Fee / Debits …” layout)
    # ------------------------------------------------------------------ #
    "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT": {
        # measured on several samples; tweak if your coordinates differ
        "column_zones": {
            "description": (  0, 260),   # “Details” text block
            # “Service Fee” column lives roughly 260‑300 – we just ignore it
            "debit":       (300, 420),
            "credit":      (420, 520),
            "balance":     (520, 999),
        },
        "amount_format": {
            "thousands_separator": ".",   # 40.929,08  -> 40929.08
            "decimal_separator":  ",",
            "negative_trailing":  "Y",    #   800,00‑  ->  -800,00
        },
        "date_format": {
            # in these PDFs the date column shows “MM DD”.  Year comes from the
            # “Statement from … to …” header, so we allow a missing year.
            "formats": ["%m %d %Y", "%m %d"],
            "year_optional": "Y",
        },
        "description": {"multiline": True},
        "date_x_threshold": 260,          # left edge of the date column
    },
}
