from django.db import migrations


def populate(apps, schema_editor):
    alias = schema_editor.connection.alias
    Ordem = apps.get_model('orders', 'Ordem')
    Endereco = apps.get_model('customers', 'EnderecoEntrega')
    orders = Ordem.objects.using(alias)
    orders.update(tipo_operacao='varejo', status_pagamento='pendente', tipo_entrega='a_combinar')
    orders.filter(completo=True).update(status='concluido')
    orders.filter(completo=False).update(status='novo')
    # Só considera endereços pertencentes à mesma loja do pedido.
    for address in Endereco.objects.using(alias).exclude(ordem_id=None).values('ordem_id', 'tenant_id'):
        orders.filter(pk=address['ordem_id'], tenant_id=address['tenant_id']).update(tipo_entrega='entrega')
    orders.filter(formade_pagamento__iexact='Retirada no local').update(tipo_entrega='retirada')


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0004_ordem_concluido_em_ordem_status_and_more'),
        ('tenants', '0019_tenantsettings_tipo_operacao'),
        ('customers', '0005_enderecoentrega_estado'),
    ]
    operations = [migrations.RunPython(populate, migrations.RunPython.noop)]
