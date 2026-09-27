from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from orders.models import Ordem
from orders.services.status import change_status, change_delivery, change_payment, get_status_label, get_whatsapp_url


def access_error(request):
    if not request.user.is_authenticated:
        return JsonResponse({'message': 'Autenticação necessária.'}, status=401)
    tenant_id = getattr(request.user, 'tenant_id', None)
    host_tenant = getattr(request, 'tenant', None)
    if not tenant_id or (host_tenant is not None and host_tenant.pk != tenant_id):
        return JsonResponse({'message': 'Acesso negado à loja.'}, status=403)
    return None


def _mutation(request, ordem_id, action, **kwargs):
    error = access_error(request)
    if error:
        return error
    try:
        ordem = action(ordem_id=ordem_id, tenant_id=request.user.tenant_id, usuario=request.user, **kwargs)
    except Ordem.DoesNotExist:
        return JsonResponse({'message': 'Pedido não encontrado.'}, status=404)
    except ValidationError as exc:
        return JsonResponse({'message': ' '.join(exc.messages)}, status=409)
    return JsonResponse({'status': 'ok', 'ordem_id': ordem.pk, 'order_status': ordem.status,
                         'label': get_status_label(ordem), 'whatsapp_url': get_whatsapp_url(ordem)})


@require_POST
def status(request, ordem_id):
    return _mutation(request, ordem_id, change_status,
                     novo_status=request.POST.get('status', ''),
                     expected_status=request.POST.get('status_atual', ''))


@require_POST
def cancel(request, ordem_id):
    return _mutation(request, ordem_id, change_status, novo_status='cancelado',
                     expected_status=request.POST.get('status_atual', ''))


@require_POST
def delivery(request, ordem_id):
    return _mutation(request, ordem_id, change_delivery, tipo_entrega=request.POST.get('tipo_entrega', ''))


@require_POST
def payment(request, ordem_id):
    return _mutation(request, ordem_id, change_payment, status_pagamento=request.POST.get('status_pagamento', ''))


@require_GET
def history(request, ordem_id):
    error = access_error(request)
    if error:
        return error
    try:
        ordem = Ordem.objects.get(pk=ordem_id, tenant_id=request.user.tenant_id)
    except Ordem.DoesNotExist:
        return JsonResponse({'message': 'Pedido não encontrado.'}, status=404)
    return JsonResponse({'history': [
        {'anterior': get_status_label(ordem, entry.status_anterior),
         'novo': get_status_label(ordem, entry.status_novo),
         'data': entry.alterado_em.isoformat(),
         'usuario': entry.usuario.username if entry.usuario and entry.usuario.tenant_id == ordem.tenant_id else 'Sistema',
         'observacao': entry.observacao}
        for entry in ordem.historico_status.select_related('usuario')
    ]})


@require_POST
def customer(request, ordem_id):
    from orders.services.customer import update_customer
    return _mutation(request, ordem_id, update_customer,
                     nome=request.POST.get('nome', ''),
                     whatsapp=request.POST.get('whatsapp', ''),
                     observacoes=request.POST.get('observacoes', ''))
