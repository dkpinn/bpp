# rules.py

PARSING_RULES = {
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {
        "date_x_threshold": 90,
        "column_zones": {
            "description": (90, 305),
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
            "formats": ["%d/%m/%Y", "%m %d"],
            "year_optional": "Y"
        },
        "description": {
            "multiline": True
        },
        "multiline_description": True,
        "parse_rules_applied": [
            "x-coordinate zone-based classification",
            "multiline description parsing",
            "debit/credit/balance alignment checks",
            "amount format normalization",
            "balance delta validation",
            "support for missing year in date",
            "handling of trailing dash for negatives"
        ]
    },
    # Add more configurations like:
    # "ABSA_CREDIT_CARD_STATEMENT": {...},
    # "STANDARD_BANK_CHEQUE_ACCOUNT_STATEMENT": {...},
}
