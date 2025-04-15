# rules.py

PARSING_RULES = {
    "ABSA_CHEQUE_ACCOUNT_STATEMENT": {
        "date_x_threshold": 95,
        "column_zones": {
            "description": (85, 295),
            "debit": (330, 450),
            "credit": (455, 510),
            "balance": (515, 999)
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
        "multiline_description": True,
        "parse_rules_applied": [
            "x-coordinate zone-based classification",
            "multiline description parsing",
            "debit/credit/balance alignment checks",
            "amount format normalization",
            "balance delta validation",
            "support for missing year in date",
            "handling of trailing dash for negatives",
            "remove amount/balance from description when wrongly included"
        ]
    },
    # Add more configurations like:
    # "ABSA_CREDIT_CARD_STATEMENT": {...},
    # "STANDARD_BANK_CHEQUE_ACCOUNT_STATEMENT": {...},
}
