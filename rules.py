# rules.py

PARSING_RULES = {
    # ---------------------------------------------------------------------
    # ABSA – Cheque Account
    # ---------------------------------------------------------------------
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {
        "column_zones": {
            "description": (95, 305),
            "debit":       (310, 390),
            "credit":      (395, 470),
            "balance":     (475, 999),
        },
        "amount_format": {
            "thousands_separator": " ",
            "decimal_separator":   ".",
            "negative_trailing":   "N",
        },
        "date_format": {
            "formats":       ["%d/%m/%Y"],
            "year_optional": "N",
        },
        "description": {
            "multiline": True,
        },
        "date_x_threshold": 95,
        "output_order": ["date", "description", "amount", "balance"],
    },

    # ---------------------------------------------------------------------
    # Standard Bank – Business Current Account
    # ---------------------------------------------------------------------
    "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT": {
        "column_zones": {
            "description": (0, 317.52),           # 0 to 4.41 in
            "debit":       (317.52, 358.56),      # 4.41 to 4.98 in
            "credit":      (358.56, 402.48),      # 4.98 to 5.59 in
            "date":        (402.48, 433.44),      # 5.59 to 6.02 in
            "balance":     (433.44, 999),         # 6.02 in to end
        },
        "amount_format": {
            "thousands_separator": ".",
            "decimal_separator":   ",",
            "negative_trailing":   "Y",
        },
        "date_format": {
            "formats": ["%m %y"],
            "year_optional": "Y",
        },
        "description": {
            "multiline": True,
        },
        "date_x_threshold": 402.48,
        "output_order": ["date", "description", "amount", "balance"],
    },
}
