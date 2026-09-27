import logging
import re
from decimal import Decimal

from whatsapp.messages import PROCESSOS
from whatsapp.models import MensagemProcesso
from whatsapp.services.evolution import EvolutionError, EvolutionService, instance_name


logger = logging.getLogger(__name__)


def _default_message(scenario, status):
    for process_status, _title, _icon, message in PROCESSOS.get(scenario, []):
        if process_status == status:
            return message
    return ''


def _recipient(order):
    if not order.cliente or order.cliente.tenant_id != order.tenant_id:
        return ''
    number = re.sub(r'\D', '', order.cliente.telefone or '')
    if len(number) in (10, 11):
        number = f'55{number}'
    return number if 12 <= len(number) <= 15 else ''


def _currency(value):
    rendered = f'{Decimal(value or 0):,.2f}'
    return f'R$ {rendered.replace(",", "_").replace(".", ",").replace("_", ".")}'


def render_process_message(order, template):
    settings = getattr(order.tenant, 'settings', None)
    subtotal = order.valor_total
    if subtotal is None:
        subtotal = order.get_car_total
    total = Decimal(subtotal or 0) + Decimal(order.tx_entrega or 0)
    delivery = dict(order.TipoEntrega.choices).get(order.tipo_entrega, order.tipo_entrega)

    # Importação local evita dependência circular durante a carga dos serviços.
    from orders.services.status import get_status_label

    values = {
        'cliente': order.cliente.nome if order.cliente else 'cliente',
        'pedido': str(order.pk),
        'telefone': order.cliente.telefone if order.cliente else '',
        'total': _currency(total),
        'loja': (getattr(settings, 'nome_loja', '') or order.tenant.name),
        'status': get_status_label(order),
        'entrega': delivery,
        'forma_pagamento': order.formade_pagamento or 'Não informada',
        'status_pagamento': order.get_status_pagamento_display(),
    }
    rendered = template
    for variable, value in values.items():
        rendered = rendered.replace(f'{{{variable}}}', str(value))
    return rendered


def send_order_status_message(order_id):
    """Envia a mensagem configurada; falhas não alteram o status do pedido."""
    from orders.models import Ordem

    order = (Ordem.objects.select_related('tenant', 'tenant__settings', 'cliente')
             .get(pk=order_id))
    recipient = _recipient(order)
    if not recipient:
        logger.info('WhatsApp não enviado para o pedido %s: cliente sem telefone válido.', order.pk)
        return False

    configured = MensagemProcesso.objects.filter(
        tenant_id=order.tenant_id,
        cenario=order.tipo_operacao,
        status_pedido=order.status,
    ).first()
    if configured and not configured.ativa:
        logger.info('WhatsApp desativado para o pedido %s no status %s.', order.pk, order.status)
        return False

    template = configured.mensagem if configured else _default_message(order.tipo_operacao, order.status)
    if not template:
        logger.info('WhatsApp não enviado para o pedido %s: mensagem não configurada.', order.pk)
        return False

    try:
        service = EvolutionService()
        state = service.connection_state(order.tenant)
        if not state.connected:
            logger.warning(
                'WhatsApp não enviado para o pedido %s: instância %s está %s.',
                order.pk, instance_name(order.tenant), state.state,
            )
            return False
        response = service._request(
            'POST',
            f'/message/sendText/{instance_name(order.tenant)}',
            json={'number': recipient, 'text': render_process_message(order, template)},
        )
    except EvolutionError as exc:
        logger.warning('WhatsApp não enviado para o pedido %s: %s', order.pk, exc)
        return False

    key = response.get('key', {}) if isinstance(response, dict) else {}
    logger.info('WhatsApp do pedido %s aceito pela Evolution. ID: %s', order.pk, key.get('id', '-'))
    return bool(key.get('id'))


def send_payment_status_message(order_id):
    """Envia a mensagem configurada para o estado atual do pagamento."""
    from orders.models import Ordem

    order = (Ordem.objects.select_related('tenant', 'tenant__settings', 'cliente')
             .get(pk=order_id))
    recipient = _recipient(order)
    if not recipient:
        logger.info('WhatsApp de pagamento não enviado para o pedido %s: telefone inválido.', order.pk)
        return False

    configured = MensagemProcesso.objects.filter(
        tenant_id=order.tenant_id,
        cenario='pagamento',
        status_pedido=order.status_pagamento,
    ).first()
    if configured and not configured.ativa:
        logger.info(
            'WhatsApp de pagamento desativado para o pedido %s no status %s.',
            order.pk, order.status_pagamento,
        )
        return False

    template = configured.mensagem if configured else _default_message('pagamento', order.status_pagamento)
    if not template:
        logger.info('WhatsApp de pagamento não enviado para o pedido %s: mensagem ausente.', order.pk)
        return False

    try:
        service = EvolutionService()
        state = service.connection_state(order.tenant)
        if not state.connected:
            logger.warning(
                'WhatsApp de pagamento não enviado para o pedido %s: instância %s está %s.',
                order.pk, instance_name(order.tenant), state.state,
            )
            return False
        response = service._request(
            'POST',
            f'/message/sendText/{instance_name(order.tenant)}',
            json={'number': recipient, 'text': render_process_message(order, template)},
        )
    except EvolutionError as exc:
        logger.warning('WhatsApp de pagamento não enviado para o pedido %s: %s', order.pk, exc)
        return False

    key = response.get('key', {}) if isinstance(response, dict) else {}
    logger.info(
        'WhatsApp de pagamento do pedido %s aceito pela Evolution. ID: %s',
        order.pk, key.get('id', '-'),
    )
    return bool(key.get('id'))
