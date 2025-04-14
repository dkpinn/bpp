# rules.py

PARSING_RULES = {
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {
        "date_x_threshold": 95,
        "column_zones": {
            "description": (95, 305),
            "debit": (310, 390),
            "credit": (395, 470),
            "balance": (475, 999)
        },
        "amount_format": {
            "thousands_separator": " ",
            "decimal_separator": ".",
            "negative_trailing": "Y"
        },
        "date_format": {
            "formats": ["%d/%m/%Y", "%m %d"],
            "year_optional": "Y"
        },
        "description": {
            "multiline": True
        },
        "multiline_description": True  # To implement this, update main.py so that when parsing blocks, lines without a date but within the description x-range are appended to the previous transaction’s description
    },
    # Add more configurations like:
    # "ABSA_CREDIT_CARD_STATEMENT": {...},
    # "STANDARD_BANK_CHEQUE_ACCOUNT_STATEMENT": {...},
}
