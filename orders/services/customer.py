import re
from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.auth.hashers import make_password
from customers.models import Cliente
from orders.models import Ordem
from .status import _check_user


@transaction.atomic
def update_customer(*, ordem_id, tenant_id, usuario, nome, whatsapp, observacoes):
    _check_user(usuario, tenant_id)
    ordem = Ordem.objects.select_for_update().get(pk=ordem_id, tenant_id=tenant_id)
    nome = nome.strip()
    phone = re.sub(r'\D', '', whatsapp)
    if not nome or len(nome) > 200:
        raise ValidationError('Informe o nome do cliente, com até 200 caracteres.')
    if len(phone) in (10, 11):
        phone = '55' + phone
    if not (phone.startswith('55') and len(phone) in (12, 13)):
        raise ValidationError('Informe um WhatsApp válido com DDD.')
    if len(observacoes) > 2000:
        raise ValidationError('As observações devem ter até 2000 caracteres.')
    if ordem.cliente_id:
        cliente = Cliente.objects.select_for_update().filter(pk=ordem.cliente_id, tenant_id=tenant_id).first()
        if not cliente:
            raise ValidationError('Cliente não pertence a esta loja.')
        cliente.nome = nome
        cliente.telefone = phone
        cliente.save(update_fields=['nome', 'telefone'])
    else:
        cliente = Cliente.objects.create(tenant_id=tenant_id, nome=nome, telefone=phone,
                                         senha=make_password(None), email='')
    ordem.cliente = cliente
    ordem.observacoes = observacoes.strip()
    ordem.save(update_fields=['cliente', 'observacoes'])
    return ordem
