import logging
import re

from django.contrib import messages as django_messages
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from core.utils import get_tenant_url
from orders.models import Ordem
from .messages import PROCESSOS, VARIAVEIS, mensagens_do_tenant
from .models import MensagemProcesso, WhatsAppConfiguracao
from .services.evolution import EvolutionError, EvolutionService, extract_qr_code, instance_name


logger = logging.getLogger(__name__)


def _tenant(request):
    if not request.user.is_authenticated:
        return None
    tenant = getattr(request, 'tenant', None)
    user_tenant = getattr(request.user, 'tenant', None)
    # No domínio principal (viazap.net, localhost ou túnel), o middleware deixa
    # request.tenant vazio. O painel pode então usar apenas o tenant do usuário
    # autenticado. Em um subdomínio de loja, a igualdade abaixo continua obrigatória.
    if tenant is None and user_tenant is not None:
        tenant = user_tenant
        request.tenant = tenant
    if tenant is None or user_tenant is None or tenant.pk != user_tenant.pk:
        raise Http404('Loja não encontrada.')
    return tenant


def _configuration(tenant):
    config, _ = WhatsAppConfiguracao.objects.get_or_create(
        tenant=tenant,
        defaults={'instance_name': instance_name(tenant)},
    )
    return config


def _number_from_instance(data):
    if not isinstance(data, dict):
        return ''
    instance = data.get('instance', data)
    if not isinstance(instance, dict):
        return ''
    raw = str(instance.get('ownerJid') or instance.get('number') or '')
    return re.sub(r'\D', '', raw.split('@')[0])


def _sync_state(tenant, config, service):
    state = service.connection_state(tenant)
    if state.connected:
        number = re.sub(r'\D', '', state.number)
        if not number:
            number = _number_from_instance(service.find_instance(tenant))
        config.status = WhatsAppConfiguracao.Status.CONECTADO
        config.numero_whatsapp = number
        config.conectado_em = config.conectado_em or timezone.now()
        config.save(update_fields=['instance_name', 'status', 'numero_whatsapp', 'conectado_em', 'atualizado_em'])
    elif state.state == 'missing':
        config.status = WhatsAppConfiguracao.Status.DESCONECTADO
        config.numero_whatsapp = ''
        config.conectado_em = None
        config.save(update_fields=['instance_name', 'status', 'numero_whatsapp', 'conectado_em', 'atualizado_em'])
    elif config.status == WhatsAppConfiguracao.Status.CONECTADO:
        config.status = WhatsAppConfiguracao.Status.DESCONECTADO
        config.numero_whatsapp = ''
        config.conectado_em = None
        config.save(update_fields=['instance_name', 'status', 'numero_whatsapp', 'conectado_em', 'atualizado_em'])
    return state


def painel_whatsapp(request):
    if not request.user.is_authenticated:
        return redirect('login')
    tenant = _tenant(request)
    config = _configuration(tenant)
    error = ''
    if config.status != WhatsAppConfiguracao.Status.DESCONECTADO:
        try:
            _sync_state(tenant, config, EvolutionService())
        except EvolutionError as exc:
            error = str(exc)
    return render(request, 'whatsapp/configuracao.html', {
        'localizacao': [{'n1': 'WhatsApp', 'url': 'painel_whatsapp'}],
        'qt_items_cliente': Ordem.objects.filter(tenant=tenant).count(),
        'url_marketplace': get_tenant_url(request, '/loja/'),
        'whatsapp_config': config,
        'evolution_error': error,
        'mensagens_processos': mensagens_do_tenant(tenant),
        'variaveis_mensagem': VARIAVEIS,
        'cenario_atual': getattr(getattr(tenant, 'settings', None), 'tipo_operacao', 'varejo'),
    })


@require_POST
def salvar_mensagens(request):
    if not request.user.is_authenticated:
        return redirect('login')
    tenant = _tenant(request)
    with transaction.atomic():
        for cenario, processos in PROCESSOS.items():
            for status_pedido, _titulo, _icone, padrao in processos:
                prefixo = f'{cenario}_{status_pedido}'
                mensagem = request.POST.get(f'mensagem_{prefixo}', '').strip()
                if not mensagem:
                    mensagem = padrao
                MensagemProcesso.objects.update_or_create(
                    tenant=tenant,
                    cenario=cenario,
                    status_pedido=status_pedido,
                    defaults={
                        'mensagem': mensagem[:1200],
                        'ativa': request.POST.get(f'ativa_{prefixo}') == 'on',
                    },
                )
    django_messages.success(request, 'Mensagens automáticas salvas com sucesso.')
    return redirect('painel_whatsapp')


@require_POST
def conectar(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Autenticação necessária.'}, status=403)
    tenant = _tenant(request)
    config = _configuration(tenant)
    config.status = WhatsAppConfiguracao.Status.PREPARANDO
    config.save(update_fields=['instance_name', 'status', 'atualizado_em'])
    try:
        service = EvolutionService()
        payload = service.create_instance(tenant)
        state = service.connection_state(tenant)
        if state.connected:
            _sync_state(tenant, config, service)
            return JsonResponse({'status': 'conectado', 'numero': config.numero_whatsapp})
        qr_code = extract_qr_code(payload)
        if not qr_code:
            qr_code = extract_qr_code(service.connect(tenant))
        if not qr_code:
            raise EvolutionError('O QR Code ainda não ficou disponível. Tente novamente.')
        config.status = WhatsAppConfiguracao.Status.AGUARDANDO_QR
        config.save(update_fields=['instance_name', 'status', 'atualizado_em'])
        return JsonResponse({'status': 'aguardando_qr', 'qr_code': qr_code})
    except EvolutionError as exc:
        config.status = WhatsAppConfiguracao.Status.ERRO
        config.save(update_fields=['instance_name', 'status', 'atualizado_em'])
        return JsonResponse({'status': 'erro', 'error': str(exc)}, status=503)


@require_GET
def status(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Autenticação necessária.'}, status=403)
    tenant = _tenant(request)
    config = _configuration(tenant)
    try:
        state = _sync_state(tenant, config, EvolutionService())
        if state.connected:
            return JsonResponse({'status': 'conectado', 'numero': config.numero_whatsapp})
        if state.state == 'missing':
            return JsonResponse({'status': 'desconectado'})
        return JsonResponse({'status': 'aguardando_qr'})
    except EvolutionError as exc:
        return JsonResponse({'status': 'erro', 'error': str(exc)}, status=503)


@require_POST
def desconectar(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Autenticação necessária.'}, status=403)
    tenant = _tenant(request)
    config = _configuration(tenant)
    try:
        EvolutionService().logout(tenant)
    except EvolutionError as exc:
        return JsonResponse({'status': 'erro', 'error': str(exc)}, status=503)
    config.status = WhatsAppConfiguracao.Status.DESCONECTADO
    config.numero_whatsapp = ''
    config.conectado_em = None
    config.save(update_fields=['instance_name', 'status', 'numero_whatsapp', 'conectado_em', 'atualizado_em'])
    return JsonResponse({'status': 'desconectado'})
