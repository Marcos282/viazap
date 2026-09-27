from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.crypto import get_random_string
from django.utils import timezone
from django.urls import reverse

from customers.models import Cliente, EnderecoEntrega
from orders.models import Ordem, OrdemItem
from menu.models import Produto
from tenants.models import TenantSettings


def cadastro_form(request):
    tenant = getattr(request, 'tenant', None)
    config = TenantSettings.load(tenant=tenant) if tenant else None
    if not config or not config.delivery:
        return redirect('sacola')

    cart = request.session.get('cart', {})
    produtos_carrinho = []
    subtotal = 0
    total_itens = 0
    for produto_id, quantidade in cart.items():
        produto = Produto.objects.filter(id=produto_id, tenant=tenant).first()
        if not produto:
            continue
        valor = produto.price * quantidade
        produtos_carrinho.append({
            'nome': produto.nome,
            'referencia': produto.referencia,
            'quantidade': quantidade,
            'preco_unitario': produto.price,
            'valor': valor,
        })
        subtotal += valor
        total_itens += quantidade

    taxa_entrega = config.taxa_entrega or 0.0
    return render(request, 'loja/pedidodelivery.html', {
        'config': config,
        'produtos_carrinho': produtos_carrinho,
        'subtotal': subtotal,
        'taxa_entrega': taxa_entrega,
        'total': float(subtotal) + float(taxa_entrega),
        'total_itens': total_itens,
        'color_theme': config.color_theme or '#DD7B0A',
    })


@transaction.atomic
def pedido_delivery(request):
    if request.method == 'POST' and any(
        type(qty) is not int or qty < 1 for qty in request.session.get('cart', {}).values()
    ):
        return JsonResponse({'message': 'Quantidade inválida na sacola.'}, status=400)
    if request.method != 'POST':
        return redirect('cadastro_form')

    tenant = request.tenant
    config = TenantSettings.load(tenant=tenant)
    if not config.delivery:
        return redirect('sacola')
    if not request.session.get('cart'):
        return redirect('sacola')
    cliente = Cliente.objects.create(
        tenant=tenant,
        telefone=request.POST.get('whatsapp') or '0000000000',
        nome=request.POST.get('nome') or 'Cliente sem nome',
        email=f"{request.POST.get('whatsapp') or 'cliente'}@fake.com",
        senha=get_random_string(12),
    )
    ordem = Ordem.objects.create(
        tenant=tenant,
        cliente=cliente,
        tipo_entrega=Ordem.TipoEntrega.ENTREGA,
        formade_pagamento={'1': 'Dinheiro', '2': 'Cartão de Débito', '3': 'Cartão de Crédito'}.get(request.POST.get('forma_pagamento'), 'Não informado'),
        completo=False,
        tx_entrega=config.taxa_entrega or 0.00,
        valor_total=0.00,
    )
    cart = request.session.get('cart', {})
    for produto_id, quantidade in cart.items():
        produto = get_object_or_404(Produto, id=produto_id, tenant=tenant)
        OrdemItem.objects.create(
            tenant=tenant,
            ordem=ordem,
            produto=produto,
            quantidade=quantidade,
            preco_unitario=produto.price,
        )

    itens = ordem.ordemitem_set.all()
    subtotal = sum(item.get_total for item in itens)
    ordem.valor_total = subtotal
    ordem.save(update_fields=['valor_total'])
    endereco = EnderecoEntrega.objects.create(
        tenant=tenant,
        cliente=cliente,
        ordem=ordem,
        endereco=request.POST.get('endereco_rua'),
        referencia=request.POST.get('endereco_referencia'),
        cidade=request.POST.get('cidade'),
        estado=request.POST.get('estado', ''),
        cep=request.POST.get('endereco_cep'),
        endereco_bairro=request.POST.get('endereco_bairro'),
        endereco_numero=request.POST.get('endereco_numero'),
        endereco_complemento=request.POST.get('endereco_complemento'),
    )
    request.session['last_pedido_info'] = {
        'loja': config.nome_loja,
        'pedido_id': ordem.id,
        'datahora': timezone.localtime(ordem.dataHora).strftime('%d/%m/%Y as %H:%M'),
        'nome': cliente.nome,
        'whatsapp': cliente.telefone,
        'cep': endereco.cep,
        'bairro': endereco.endereco_bairro,
        'rua': endereco.endereco,
        'complemento': endereco.endereco_complemento,
        'referencia': endereco.referencia,
        'produtos': _order_products(request, itens),
        'subtotal': float(subtotal),
        'entrega': endereco.cidade,
        'pagamento': request.POST.get('forma_pagamento', ''),
        'total': float(subtotal) + float(config.taxa_entrega or 0),
        'telefone_loja': config.whatsapp,
    }
    request.session['cart'] = {}
    response = redirect('checkout_sucesso')
    response.set_cookie('telefone_cliente', cliente.telefone, max_age=60 * 60 * 24 * 30)
    return response


def _order_products(request, items):
    return [{
        'nome': item.produto.nome if item.produto else '',
        'referencia': item.produto.referencia if item.produto else '',
        'quantidade': item.quantidade,
        'valor': float(item.get_total or 0),
        'preco': float(item.preco_unitario or 0),
        'descricao': item.produto.description if item.produto else '',
        'imagem': request.build_absolute_uri(
            (item.produto.image or item.produto.imagem_extra).url
        ) if item.produto and (item.produto.image or item.produto.imagem_extra) else '',
        'link': request.build_absolute_uri(
            reverse('detalhe', args=[item.produto.id])
        ) if item.produto else '',
    } for item in items]


@csrf_exempt
def pedido_balcao(request):
    return redirect('sacola')


@transaction.atomic
def pedido_whatsapp(request):
    if request.method == 'POST' and any(
        type(qty) is not int or qty < 1 for qty in request.session.get('cart', {}).values()
    ):
        return JsonResponse({'message': 'Quantidade inválida na sacola.'}, status=400)
    if request.method != 'POST':
        return redirect('sacola')

    tenant = request.tenant
    config = TenantSettings.load(tenant=tenant)
    cart = request.session.get('cart', {})
    vendedor = request.POST.get('vendedor', '').strip() or 'Nao informado'
    if not cart:
        return redirect('sacola')

    ordem = Ordem.objects.create(
        tenant=tenant,
        completo=False,
        tx_entrega=0.00,
        valor_total=0.00,
        tipo_entrega=Ordem.TipoEntrega.A_COMBINAR,
        formade_pagamento='Contato pelo WhatsApp',
        vendedor=vendedor,
    )
    produtos = []
    subtotal = 0
    for produto_id, quantidade in cart.items():
        produto = get_object_or_404(Produto, id=produto_id, tenant=tenant)
        item = OrdemItem.objects.create(
            tenant=tenant,
            ordem=ordem,
            produto=produto,
            quantidade=quantidade,
            preco_unitario=produto.price,
        )
        subtotal += item.get_total
        produtos.append({
            'nome': produto.nome,
            'referencia': produto.referencia,
            'quantidade': quantidade,
            'valor': float(item.get_total),
            'preco': float(produto.price),
            'descricao': produto.description or '',
            'imagem': request.build_absolute_uri(
                (produto.image or produto.imagem_extra).url
            ) if (produto.image or produto.imagem_extra) else '',
            'link': request.build_absolute_uri(reverse('detalhe', args=[produto.id])),
        })

    ordem.valor_total = subtotal
    ordem.save(update_fields=['valor_total'])
    request.session['last_pedido_info'] = {
        'loja': config.nome_loja,
        'pedido_id': ordem.id,
        'datahora': timezone.localtime(ordem.dataHora).strftime('%d/%m/%Y as %H:%M'),
        'nome': 'Contato pelo WhatsApp',
        'whatsapp': '',
        'vendedor': vendedor,
        'produtos': produtos,
        'subtotal': float(subtotal),
        'entrega': 'A combinar',
        'pagamento': 'A combinar pelo WhatsApp',
        'total': float(subtotal),
        'telefone_loja': config.whatsapp,
    }
    request.session['cart'] = {}
    return redirect('checkout_sucesso')
