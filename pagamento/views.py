"""Views do fluxo de renovação de assinatura pelo Mercado Pago.

Este módulo cria preferências do Checkout Pro, recebe os redirecionamentos
do gateway, processa notificações de webhook e entrega o último webhook ao
painel autenticado.
"""

# Biblioteca padrão usada para serialização, logs e identificadores únicos.
from datetime import timedelta
import logging
import json
import uuid

# Recursos HTTP, mensagens e utilitários do Django.
from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.exceptions import ImproperlyConfigured
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# Regras e integrações internas do projeto.
from customers.models import User
from core.utils import calcular_dias_restantes, get_tenant_url, gravar_os_dias, somar_data_expiracao
from pagamento.mercadopago_client import (
    buscar_pagamento,
    get_access_token,
    get_sdk,
    validar_assinatura_webhook,
)

from core.utils import calcular_dias_restantes, estender_expiracao, normalizar_datetime,somar_data_expiracao
from pagamento.models import Pagamento
from tenants.models import Configuracao


# Logger identificado pelo caminho deste módulo: ``pagamento.views``.
logger = logging.getLogger(__name__)


def _url_absoluta(config, nome_rota):
    """Monta a URL pública de uma rota usando o domínio de Configuracao.

    Usar o domínio cadastrado (em vez do host da requisição) evita back_urls
    e notification_url erradas em testes locais feitos por túnel (ex: ngrok).
    """
    dominio = (config.dominio or '').strip().rstrip('/')
    esquema = 'http' if dominio.startswith(('localhost', '127.0.0.1')) else 'https'
    url = f'{esquema}://{dominio}{reverse(nome_rota)}'
    logger.debug('URL absoluta montada para %s: %s', nome_rota, url)
    return url


def pagamento(request):
    """Exibe a renovação e cria uma preferência no Mercado Pago via POST.

    Requer usuário autenticado. No envio, registra localmente a tentativa,
    cria a preferência remota e redireciona o cliente ao Checkout Pro. No
    acesso GET, monta os dados de assinatura e o último webhook do usuário.
    """
    # Registra o início da requisição sem incluir credenciais do gateway.
    logger.debug('Requisição %s recebida em /pagamento por %s', request.method, request.user)

    # A tela pertence ao painel e não deve ser acessada anonimamente.
    if not request.user.is_authenticated:
        return redirect('login')

    # Reutiliza o usuário autenticado e a configuração singleton do sistema.
    user = request.user
    config = Configuracao.load()

    # Um POST representa a solicitação de criação de uma nova cobrança.
    if request.method == 'POST':
        # Registra a tentativa; o formulário simplificado não envia mais campos sensíveis.
        logger.info('POST de pagamento recebido: usuário=%s', user.pk)

        # Obtém e valida o Access Token antes de criar qualquer pagamento remoto.
        try:
            access_token = get_access_token()
        except ImproperlyConfigured as error:
            # Devolve uma mensagem amigável quando a credencial está ausente ou inválida.
            logger.warning('Pagamento recusado: %s', error)
            messages.error(request, str(error))
            return redirect('pagamento')

        # O valor vem da configuração do servidor, nunca de um valor enviado pelo cliente.
        valor = config.valor_mensalidade
        # A referência única conecta preferência, pagamento, webhook e usuário.
        external_reference = f'renovacao-{user.pk}-{uuid.uuid4().hex}'

        # Persiste a tentativa antes da chamada externa para manter rastreabilidade.
        pagamento_registro = Pagamento.objects.create(
            nr_cobranca=external_reference,
            tenant=user.tenant,
            user=user,
            valor=valor,
            # Checkout Pro deixa o pagador escolher o método na própria tela do Mercado Pago.
            forma_pagamento='pix',
            external_reference=external_reference,
            dias_creditados=config.dias_gratuitos,
        )

        # URLs absolutas usam o domínio cadastrado em Configuracao (ver `_url_absoluta`).
        success_url = _url_absoluta(config, 'pagamento_sucesso')

        # Payload oficial da preferência do Checkout Pro.
        preference_data = {
            # Item cobrado na renovação da assinatura.
            'items': [
                {
                    'id': 'renovacao-assinatura',
                    'title': 'Renovação de Assinatura',
                    'quantity': 1,
                    'unit_price': float(valor),
                    'currency_id': 'BRL',
                }
            ],
            # Sem 'payer' pré-preenchido: o e-mail real do usuário não corresponde a uma
            # conta do Mercado Pago (produção) nem a um comprador de teste (sandbox), e
            # enviá-lo causa a página de erro "/fatal/" no checkout. O pagador se
            # identifica/loga diretamente na tela do Mercado Pago.
            # Referência usada para localizar o Pagamento quando chegar o webhook.
            'external_reference': external_reference,
            # Destinos utilizados após aprovação, falha ou pendência no checkout.
            'back_urls': {
                'success': success_url,
                'failure': _url_absoluta(config, 'pagamento_falha'),
                'pending': _url_absoluta(config, 'pagamento_pendente'),
            },
            # Endpoint público em que o Mercado Pago enviará as notificações.
            'notification_url': _url_absoluta(config, 'webhook_mercadopago'),
        }

        # O retorno automático requer uma URL pública; localhost não é acessível pelo gateway.
        if not success_url.startswith(('http://localhost', 'http://127.0.0.1')):
            preference_data['auto_return'] = 'approved'

        # Guarda uma cópia formatada do payload exatamente como será enviado.
        request.session['mercadopago_request_json'] = json.dumps(
            preference_data,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        # Informa a tentativa sem registrar o Access Token nos logs.
        logger.info('Criando preferência para usuário=%s valor=%s', user.pk, valor)

        # O cliente centralizado cria a preferência usando o Access Token validado.
        preference_response = get_sdk().preference().create(preference_data)
        # O SDK separa metadados HTTP do corpo retornado pela API.
        preference = preference_response.get('response', {})
        logger.info(
            'Resposta da preferência do Mercado Pago: status=%s resposta=%s',
            preference_response.get('status'),
            preference,
        )

        # Guarda a resposta formatada para exibição única no próximo GET da página.
        request.session['mercadopago_preference_json'] = json.dumps(
            preference_response,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        # Apenas HTTP 200/201 representa criação aceita pelo Mercado Pago.
        if preference_response.get('status') not in (200, 201):
            # Marca localmente a falha para não deixar a tentativa como pendente.
            pagamento_registro.status = 'rejected'
            pagamento_registro.save(update_fields=['status', 'data_atualizacao'])
            logger.error('Falha ao criar preferência: %s', preference_response)
            messages.error(request, 'Não foi possível gerar o pagamento.')
            return redirect('pagamento')

        if pagamento_registro.status == 'success':
            somar_data_expiracao(user)
            user.refresh_from_db(fields=['data_expiracao'])

        # Tokens TEST usam a URL sandbox; tokens APP_USR usam a URL de produção.
        is_sandbox = access_token.startswith('TEST-')
        checkout_url = (
            preference.get('sandbox_init_point')
            if is_sandbox
            else preference.get('init_point')
        )
        
        # Impede um redirecionamento vazio quando a API responde sem URL de checkout.
        if not checkout_url:
            logger.error('Preferência criada sem URL de checkout: %s', preference_response)
            messages.error(request, 'O Mercado Pago não retornou a URL de pagamento.')
            return redirect('pagamento')

        # Relaciona o registro local ao identificador da preferência remota.
        pagamento_registro.mp_preference_id = preference.get('id')
        pagamento_registro.save(
            update_fields=['mp_preference_id', 'data_atualizacao']
        )

        # Registra o destino e envia o navegador ao Checkout Pro.
        logger.info(
            'Redirecionando para checkout: preferência=%s sandbox=%s url=%s',
            preference.get('id'),
            is_sandbox,
            checkout_url,
        )
        return redirect(checkout_url)

    # Em GET, calcula quanto tempo de acesso ainda resta para o usuário.
    dias_restantes = None
    if user.data_expiracao:
        dias_restantes = calcular_dias_restantes(user.data_expiracao)

    # Recupera somente o webhook mais recente pertencente ao usuário autenticado.
    ultimo_webhook = (
        Pagamento.objects.filter(user=user, resposta_bruta__isnull=False)
        .order_by('-data_atualizacao')
        .first()
    )
    # Lista de pagamentos do usuário para seleção no dropdown de comprovantes
    pagamentos_usuario = Pagamento.objects.filter(user=user).order_by('-data_criacao')

    localizacao = [
        {"n1": "Pagamento", "url": "pagamento"},
    ]   
    # Dados usados para renderizar status, respostas temporárias e log persistido.
    context = {
        "localizacao": localizacao,
        "configuracao": config,
        "url_marketplace": get_tenant_url(request, '/loja/'),
        "dias_restantes": dias_restantes,
        "data_expiracao": user.data_expiracao,
        "pagamentos_usuario": pagamentos_usuario,
        # ``pop`` mostra a resposta uma vez e depois a remove da sessão.
        "mercadopago_request_json": request.session.pop(
            'mercadopago_request_json', None
        ),
        "mercadopago_preference_json": request.session.pop(
            'mercadopago_preference_json', None
        ),
        "mercadopago_return_json": request.session.pop(
            'mercadopago_return_json', None
        ),
        # JSON identado do último webhook, exibido abaixo do botão de pagamento.
        "webhook_json": json.dumps(
            ultimo_webhook.resposta_bruta,
            ensure_ascii=False,
            indent=2,
            default=str,
        ) if ultimo_webhook else None,
    }

    # Renderiza a página principal da renovação.
    return render(request, 'pagamento/index.html', context)


def pagamento_sucesso(request):
    """Recebe o redirecionamento de sucesso feito pelo Checkout Pro.

    Este retorno serve apenas para feedback visual. A confirmação confiável do
    status é feita pelo webhook e pela consulta autenticada à API.
    """
    # Captura os parâmetros recebidos para diagnóstico na página.
    retorno = request.GET.dict()
    logger.info('[PAGAMENTO_SUCESSO] Retorno GET aprovado do Mercado Pago: %s', retorno)

    external_reference = retorno.get('external_reference')
    status = retorno.get('status') or retorno.get('collection_status')
    logger.info('[PAGAMENTO_SUCESSO] external_reference: %s | status: %s', external_reference, status)

    if external_reference and status == 'approved':
        pagamento_registro = Pagamento.objects.filter(
            external_reference=external_reference
        ).first()
        if pagamento_registro:
            logger.info('[PAGAMENTO_SUCESSO] Registro encontrado! Status atual do pagamento no DB: %s | Usuário: %s', pagamento_registro.status, pagamento_registro.user)
            if pagamento_registro.status != 'approved':
                pagamento_registro.status = 'approved'
                pagamento_registro.save(update_fields=['status', 'data_atualizacao'])
                
                user = pagamento_registro.user
                exp_anterior = user.data_expiracao
                nova_exp = user.estender_expiracao(dias=pagamento_registro.dias_creditados or 30)
                logger.info('[PAGAMENTO_SUCESSO] Expiracao estendida com SUCESSO! Usuario: %s | Exp. Anterior: %s | Nova Exp.: %s', user.email, exp_anterior, nova_exp)
            else:
                logger.info('[PAGAMENTO_SUCESSO] Pagamento ja estava como approved no DB. Nenhuma alteracao extra feita.')
        else:
            logger.warning('[PAGAMENTO_SUCESSO] Nenhum registro de Pagamento encontrado para external_reference: %s', external_reference)
    else:
        logger.warning('[PAGAMENTO_SUCESSO] Condicao nao satisfeita. external_reference=%s, status=%s', external_reference, status)

    # Armazena temporariamente o retorno até o próximo carregamento da página.
    request.session['mercadopago_return_json'] = json.dumps(
        retorno, ensure_ascii=False, indent=2
    )
    # Exibe a mensagem e volta para a tela de pagamento.
    messages.success(request, 'Pagamento aprovado. Obrigado!')
    return redirect('pagamento')


def pagamento_falha(request):
    """Recebe o redirecionamento de pagamento recusado ou cancelado."""
    # Preserva os parâmetros de falha para exibição e depuração.
    retorno = request.GET.dict()
    logger.warning('Retorno de pagamento recusado/cancelado: %s', retorno)
    request.session['mercadopago_return_json'] = json.dumps(
        retorno, ensure_ascii=False, indent=2
    )
    # Informa a falha e retorna o usuário à tela de renovação.
    messages.error(request, 'O pagamento não foi concluído. Tente novamente.')
    return redirect('pagamento')


def pagamento_pendente(request):
    """Recebe o redirecionamento de um pagamento ainda em processamento."""
    # Preserva os parâmetros de pendência para exibição e depuração.
    retorno = request.GET.dict()
    logger.info('Retorno de pagamento pendente: %s', retorno)
    request.session['mercadopago_return_json'] = json.dumps(
        retorno, ensure_ascii=False, indent=2
    )
    # Informa que a confirmação definitiva ainda depende do webhook.
    messages.info(request, 'Pagamento pendente de confirmação.')
    return redirect('pagamento')


# O Mercado Pago não possui cookie CSRF da aplicação; a assinatura protege a origem.
@csrf_exempt
# Notificações recebidas por outros métodos HTTP são rejeitadas automaticamente.
@require_POST
def webhook_mercadopago(request):
    """Valida, consulta e persiste uma notificação do Mercado Pago.

    O payload recebido não é usado sozinho como fonte de verdade. Após validar
    a assinatura, a view consulta o pagamento diretamente na API e usa a
    ``external_reference`` retornada para localizar o registro local.
    """
    # Decodifica o corpo preservando caracteres inválidos para facilitar diagnóstico.
    conteudo_bruto = request.body.decode('utf-8', errors='replace')
    # Registra metadados relevantes para rastrear a notificação.
    logger.info(
        'Webhook recebido: query=%s request_id=%s tópico=%s corpo=%s',
        request.GET.dict(),
        request.headers.get('x-request-id'),
        request.GET.get('type') or request.GET.get('topic'),
        conteudo_bruto,
    )

    # Converte o corpo JSON e rejeita notificações malformadas.
    try:
        dados = json.loads(conteudo_bruto)
    except json.JSONDecodeError as error:
        logger.warning('Webhook do Mercado Pago com JSON inválido: %s', error)
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    # O Mercado Pago assina prioritariamente o ``data.id`` recebido na query.
    # O ID do corpo é usado como fallback para formatos alternativos de evento.
    data_id = str(
        request.GET.get('data.id')
        or (dados.get('data') or {}).get('id')
        or ''
    )

    # Rejeita a notificação quando a assinatura configurada não confere.
    if not validar_assinatura_webhook(request, data_id):
        logger.warning('Webhook do Mercado Pago com assinatura inválida.')
        return JsonResponse({'error': 'Assinatura inválida'}, status=403)

    # Consulta a API autenticada para obter o estado confiável do pagamento.
    pagamento_dados = {}
    if data_id:
        try:
            pagamento_dados = buscar_pagamento(data_id)
        except Exception:
            # Uma falha externa é registrada; o endpoint ainda pode guardar o payload.
            logger.exception('Não foi possível consultar o pagamento %s.', data_id)

    # A referência confirmada pela API tem prioridade sobre o valor do webhook.
    external_reference = (
        pagamento_dados.get('external_reference')
        or dados.get('external_reference')
    )

    # Localiza a tentativa de pagamento criada antes do redirecionamento ao checkout.
    pagamento_registro = None
    if external_reference:
        pagamento_registro = Pagamento.objects.filter(
            external_reference=external_reference
        ).first()

    # Agrupa payload, query, request ID e resposta da API para auditoria em JSON.
    webhook_log = {
        'webhook': dados,
        'query': request.GET.dict(),
        'request_id': request.headers.get('x-request-id'),
        'payment': pagamento_dados or None,
    }

    # Persiste o log e sincroniza identificador/status quando o pagamento é encontrado.
    if pagamento_registro:
        pagamento_registro.resposta_bruta = webhook_log
        user = pagamento_registro.user
        if user and user.data_expiracao:
            total = user.data_expiracao - timezone.now()
            logger.info('[WEBHOOK] Tempo restante para expiração do usuário (%s): %s', user.email, total)

        if data_id:
            pagamento_registro.mp_payment_id = data_id
        # Aceita somente estados previstos no model local.
        status = pagamento_dados.get('status')
        logger.info('[WEBHOOK] Pagamento encontrado no DB: ID=%s | Status atual: %s | Status retornado API MP: %s', pagamento_registro.id, pagamento_registro.status, status)
        if status in dict(Pagamento.STATUS_CHOICES):
            if status == 'approved' and pagamento_registro.status != 'approved':
                user = pagamento_registro.user
                exp_anterior = user.data_expiracao
                nova_exp = user.estender_expiracao(
                    dias=pagamento_registro.dias_creditados or 30
                )
                logger.info('[WEBHOOK] Expiracao estendida via Webhook! Usuario: %s | Exp. Anterior: %s | Nova Exp.: %s', user.email, exp_anterior, nova_exp)
            pagamento_registro.status = status
        pagamento_registro.save()
    else:
        logger.warning('[WEBHOOK] Nenhum pagamento local localizado para external_reference: %s', external_reference)

    # Registra a conclusão do processamento sem incluir credenciais secretas.
    logger.info(
        'Webhook processado: ação=%s tipo=%s id=%s dados=%s',
        dados.get('action'),
        dados.get('type'),
        (dados.get('data') or {}).get('id'),
        json.dumps(dados, ensure_ascii=False),
    )

    # Informa ao Mercado Pago que a notificação foi recebida e se foi associada.
    return JsonResponse(
        {
            'received': True,
            'persisted': pagamento_registro is not None,
            'data': dados,
        },
        status=200,
    )


def webhook_log(request):
    """Retorna o último webhook do usuário para atualização assíncrona da tela."""
    # Protege o histórico de pagamento contra consultas anônimas.
    if not request.user.is_authenticated:
        return JsonResponse({'detail': 'unauthorized'}, status=401)

    # O filtro por usuário impede acesso ao webhook de outro tenant/cliente.
    pagamento_registro = (
        Pagamento.objects.filter(
            user=request.user,
            resposta_bruta__isnull=False,
        )
        .order_by('-data_atualizacao')
        .first()
    )

    # Retorna ``null`` enquanto nenhuma notificação tiver sido persistida.
    return JsonResponse({
        'webhook': (
            pagamento_registro.resposta_bruta
            if pagamento_registro
            else None
        ),
        'updated_at': (
            pagamento_registro.data_atualizacao.isoformat()
            if pagamento_registro
            else None
        ),
    })


from datetime import datetime


def extrair_comprovante_amigavel(pagamento_registro, mp_dados=None):
    """Gera um dicionário formatado e amigável com os dados do comprovante."""
    mp_dados = mp_dados or {}

    # Trata data de pagamento/aprovação
    data_raw = mp_dados.get('date_approved') or mp_dados.get('date_created')
    if data_raw:
        try:
            dt = datetime.fromisoformat(str(data_raw).replace('Z', '+00:00'))
            data_str = dt.strftime('%d/%m/%Y às %H:%M:%S')
        except Exception:
            data_str = str(data_raw)
    else:
        data_str = pagamento_registro.data_criacao.strftime('%d/%m/%Y às %H:%M:%S')

    # Identificação da forma de pagamento
    tipo = mp_dados.get('payment_type_id', '')
    metodo = (mp_dados.get('payment_method_id') or '').lower()

    if tipo == 'credit_card':
        card_digits = (mp_dados.get('card') or {}).get('last_four_digits', '')
        forma_str = f"Cartão de Crédito ({metodo.upper()})" + (f" final {card_digits}" if card_digits else "")
    elif tipo in ['bank_transfer', 'pix'] or metodo == 'pix':
        forma_str = "PIX"
    elif tipo == 'ticket' or 'bol' in metodo:
        forma_str = "Boleto Bancário"
    else:
        forma_str = pagamento_registro.get_forma_pagamento_display()

    status_final = mp_dados.get('status') or pagamento_registro.status
    status_map = dict(Pagamento.STATUS_CHOICES)
    status_display = status_map.get(status_final, status_final.upper() if status_final else 'Pendente')

    comprovante_id = str(
        mp_dados.get('id')
        or pagamento_registro.mp_payment_id
        or pagamento_registro.nr_cobranca
    )

    return {
        'comprovante_id': comprovante_id,
        'referencia': pagamento_registro.external_reference,
        'empresa': pagamento_registro.tenant.name if pagamento_registro.tenant else 'Empresa',
        'usuario': pagamento_registro.user.email,
        'valor': f"R$ {pagamento_registro.valor:,.2f}".replace('.', ','),
        'status': status_final,
        'status_display': status_display,
        'forma_pagamento': forma_str,
        'data_pagamento': data_str,
        'dias_creditados': pagamento_registro.dias_creditados,
        'data_expiracao': pagamento_registro.user.data_expiracao.strftime('%d/%m/%Y') if pagamento_registro.user.data_expiracao else 'N/A',
    }


def consultar_comprovante(request):
    """Consulta o pagamento no Mercado Pago pelo ID selecionado e retorna o comprovante."""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Não autorizado'}, status=401)

    pagamento_id = request.GET.get('pagamento_id')
    if not pagamento_id:
        return JsonResponse({'error': 'Selecione um pagamento para consultar o comprovante.'}, status=400)

    # Localiza o registro de pagamento do usuário logado
    pagamento_registro = Pagamento.objects.filter(id=pagamento_id, user=request.user).first()
    if not pagamento_registro:
        return JsonResponse({'error': 'Registro de pagamento não encontrado.'}, status=404)

    # Identifica o mp_payment_id
    mp_payment_id = pagamento_registro.mp_payment_id

    # Fallback: se não estiver salvo diretamente, tenta buscar na resposta_bruta
    if not mp_payment_id and pagamento_registro.resposta_bruta:
        resp = pagamento_registro.resposta_bruta
        payment_info = resp.get('payment') or {}
        mp_payment_id = payment_info.get('id') or (resp.get('webhook') or {}).get('data', {}).get('id')

    mp_dados = {}
    if mp_payment_id:
        try:
            logger.info('[COMPROVANTE] Consultando ID %s no Mercado Pago...', mp_payment_id)
            mp_dados = buscar_pagamento(mp_payment_id)
            novo_status = mp_dados.get('status')
            if novo_status and novo_status in dict(Pagamento.STATUS_CHOICES):
                if novo_status == 'approved' and pagamento_registro.status != 'approved':
                    pagamento_registro.user.estender_expiracao(dias=pagamento_registro.dias_creditados or 30)
                pagamento_registro.status = novo_status
                pagamento_registro.mp_payment_id = str(mp_payment_id)
                pagamento_registro.save()
        except Exception as error:
            logger.warning('[COMPROVANTE] Não foi possível consultar o Mercado Pago para id=%s: %s', mp_payment_id, error)

    comprovante = extrair_comprovante_amigavel(pagamento_registro, mp_dados)
    return JsonResponse({'success': True, 'comprovante': comprovante})