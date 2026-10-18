"""Normalization and validation for new store addresses."""
import re
from django.core.exceptions import ValidationError


def normalize_shop_identifier(value):
    value = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9]{1,50}', value):
        raise ValidationError(
            'Use de 1 a 50 letras de a a z e números, sem acentos, espaços ou símbolos.'
        )
    return value.lower()
