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
    }
}
