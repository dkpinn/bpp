# rules.py

PARSING_RULES = {
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {
        "column_zones": {
            "description": (95, 305),
            "debit": (310, 390),
            "credit": (395, 470),
            "balance": (475, 999)
        },
        "amount_format": {
            "thousands_separator": " ",
            "decimal_separator": ".",
            "negative_trailing": "N"
        },
        "date_format": {
            "formats": ["%d/%m/%Y"],
            "year_optional": "N"
        },
        "description": {
            "multiline": True
        },
        "date_x_threshold": 95
    },
    "STANDARD_BANK_BUSINESS_CURRENT_ACCOUNT": {
        "column_zones": {
            "description": (0, 250),
            "debit": (300, 370),
            "credit": (375, 450),
            "balance": (455, 999)
        },
        "amount_format": {
            "thousands_separator": ".",
            "decimal_separator": ",",
            "negative_trailing": "Y"
        },
        "date_format": {
            "formats": ["%m %d"],
            "year_optional": "Y"
        },
        "description": {
            "multiline": True
        },
        "date_x_threshold": 600
    }
}
