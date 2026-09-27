import logging

import mercadopago
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from mercadopago.webhook.validator import (
    InvalidWebhookSignatureError,
    WebhookSignatureValidator,
)


logger = logging.getLogger(__name__)


def get_access_token():
    """Retorna o Access Token do Mercado Pago a partir do settings do projeto."""
    access_token = (getattr(settings, 'MERCADO_PAGO_TOKEN', '') or '').strip()
    if not access_token:
        raise ImproperlyConfigured('MERCADO_PAGO_TOKEN não configurado no settings.')
    if not access_token.startswith(('APP_USR-', 'TEST-')):
        raise ImproperlyConfigured('MERCADO_PAGO_TOKEN possui formato inválido.')
    return access_token


def get_sdk():
    return mercadopago.SDK(get_access_token())


def buscar_pagamento(mp_payment_id):
    """Consulta o status atual de um pagamento direto na API do Mercado Pago."""
    sdk = get_sdk()
    result = sdk.payment().get(mp_payment_id)
    return result["response"]


def validar_assinatura_webhook(request, data_id):
    """
    Valida o header x-signature do webhook do Mercado Pago.
    https://www.mercadopago.com.br/developers/pt/docs/checkout-api/webhooks#editor_5
    """
    secret = getattr(settings, 'MERCADOPAGO_WEBHOOK_SECRET', '').strip()
    if not secret:
        # A consulta posterior à API continua sendo a fonte de verdade do pagamento.
        logger.warning('MERCADOPAGO_WEBHOOK_SECRET não configurado; assinatura não validada.')
        return True

    try:
        WebhookSignatureValidator.validate(
            request.headers.get('x-signature'),
            request.headers.get('x-request-id'),
            data_id,
            secret,
        )
    except InvalidWebhookSignatureError:
        return False
    return True
