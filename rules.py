PARSING_RULES = {
    "ABSA_CHEQUE": {
        "bank_name": "ABSA",
        "account_type": "Cheque Account Statement",
        "column_zones": {
            "description": [95, 305],
            "debit": [310, 390],
            "credit": [395, 470],
            "balance": [475, 999]
        },
        "date_x_threshold": 95,
        "multi_line_description": True,
        "amount_comma_optional": True,
        "balance_validation_passes": 5,
        "negatives_have_dash": True
    }
}
