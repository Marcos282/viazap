from django.db import transaction
from django.urls import reverse
import json
import re
from urllib import request
from django.shortcuts import render, HttpResponse, get_object_or_404, redirect
from django.db.models import Prefetch
from menu.models import Banners, Produto, Category
from core.utils import store_share_data, product_share_data, formatar_brl, formatar_brl_noS, verificar_loja_aberta, get_tenant_url
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from orders.models import Ordem, OrdemItem
from customers.models import Cliente
from tenants.models import Tenant, TenantSettings, Configuracao
from core.ai_chat import (
    ask_ai_assistant,
    add_chat_message,
    chat_introduction,
    matching_products,
    product_details_reply,
    build_store_context,
    chat_session_belongs_to_tenant,
    ensure_chat_session_state,
    get_chat_session,
    get_chat_messages,
    list_active_chat_sessions,
    reset_idle_operator_session,
    set_chat_session_mode,
)
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import uuid
import os
from django.conf import settings


def inicial(request):
    """
    Renderiza a página inicial do site.
    """
    return render(request, 'inicial.html')

def home_view(request):
    if getattr(request, 'tenant', None) is not None:
        return redirect('/loja/')
    return render(request, 'inicial.html')

# Funções utilitárias de sessão
def get_cart(request):
    return request.session.get('cart', {})

def get_qdt_prod(request):
    qtd_prod = get_cart(request)
    return len(qtd_prod)

def save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True

def get_categorias(request):
    return  Category.objects.filter(tenant=request.tenant)   

def loja(request):
   qtd_prd = get_qdt_prod(request)
   categoria_id = request.GET.get("categoria_id")
   termo_busca = request.GET.get("busca", "").strip()
   configuracao = TenantSettings.objects.filter(tenant=request.tenant).first()
   analytics_tag = (configuracao.tag_google_analytics or '').strip().upper() if configuracao else ''
   if not analytics_tag and configuracao:
       analytics_tag = (configuracao.googleanalytics or '').strip().upper()
   ga_measurement_id = analytics_tag if re.fullmatch(r'G-[A-Z0-9]+', analytics_tag) else ''
   gtm_container_id = analytics_tag if re.fullmatch(r'GTM-[A-Z0-9]+', analytics_tag) else ''
   configuracao_extra = Configuracao.load()
   categorias = Category.objects.filter(
       tenant=request.tenant,
   ).order_by('ordem', 'name')
   categoria_selecionada = categorias.filter(id=categoria_id).first() if categoria_id else None
   produtos = Produto.objects.filter(
       tenant=request.tenant,
   ).order_by('ordem_exibicao', 'nome')

   if termo_busca:
       produtos = produtos.filter(nome__icontains=termo_busca)

   if categoria_selecionada:
       produtos = produtos.filter(category=categoria_selecionada)

   categorias = categorias.prefetch_related(
       Prefetch('produto_set', queryset=produtos, to_attr='produtos_visiveis')
   )

   for categoria in categorias:
       for produto in categoria.produtos_visiveis:
           produto.preco_formatado = formatar_brl(produto.price)

   # Pega o carrinho da sessão
   cart = request.session.get('cart', {})
   cart_count = sum(cart.values())
    
   telefone_cookie = request.COOKIES.get('telefone_cliente', '')
   cliente = None
   ordens_pendentes = 0
   if telefone_cookie and request.tenant:
       cliente = Cliente.objects.filter(
           tenant=request.tenant, telefone=telefone_cookie,
       ).first()
       if cliente:
           ordens_pendentes = cliente.ordem_set.filter(
               tenant=request.tenant, completo=False,
           ).count()

   # Verifica se existe TenantSettings para o tenant
   if TenantSettings.objects.filter(tenant=request.tenant).exists():
       config = TenantSettings.load(tenant=request.tenant)
       if config.is_open_now():
           aberto = True
       else:
           aberto = False
       # Pega o horário de fechamento para hoje
       hora_fechamento = config.get_hora_fechamento_hoje()
       if hora_fechamento and hasattr(hora_fechamento, 'strftime'):
           hora_fechamento = hora_fechamento.strftime('%H:%M')
           hora_fechamento = f"Fecha hoje às {hora_fechamento}h"
       else:
           hora_fechamento = 'Não abre hoje'
   else:
       config = None
       aberto = False
       hora_fechamento = 'Configuração pendende'

   funcionamento = verificar_loja_aberta(request)
   print(f"🟢 DEBUG LOJA VIEW: {funcionamento['status_texto']}")
   print(f"🟢 DEBUG LOJA ABERTA ?: {funcionamento['is_open']}")

   aberto = funcionamento['is_open']


   context = {
       'store_share': store_share_data(request, request.tenant, configuracao, configuracao_extra) if request.tenant else None,
       'configuracao_extra': configuracao_extra,
       'configuracao': configuracao_extra,
       'settings': configuracao,
       'ga_measurement_id': ga_measurement_id,
       'gtm_container_id': gtm_container_id,
       'banners': Banners.objects.filter(
           tenant=request.tenant,
           ativo=True,
       ).order_by('ordem_exibicao'),
       'categorias': categorias,
      'categoria_selecionada': categoria_selecionada,
       'cart_count': cart_count,
       'qtd_prd': len(cart),
       'telefone_cookie': telefone_cookie,
       'dados_cliente': cliente,
       'ordens_pendentes': ordens_pendentes,
       'config': config,
       'aberto': aberto,
       'hora_fechamento': hora_fechamento,
       'termo_busca': termo_busca,
       'color_theme': config.color_theme if config else '#ff5900',  # Cor do tema ou padrão laranja
    }
   print(f"Total>>>>> {get_qdt_prod(request)}")
   print(f"Cliente>>>>> {telefone_cookie}")
   return render(request, 'loja/index.html', context=context)


#detalhe =====================================================================
def detalhe(request,produto_id):
    produto = get_object_or_404(Produto, tenant=request.tenant, id=produto_id)
    valor_br = formatar_brl(produto.price)
    valor_br_semS = formatar_brl_noS(produto.price)
    cart = get_cart(request)
    cart_count = sum(cart.values())

    print(f" contador: {cart_count}")

    categorias = get_categorias(request)
    imagens_galeria = list(produto.imagens.all().order_by('ordem'))
    config = TenantSettings.objects.filter(tenant=request.tenant).first()
    configuracao = Configuracao.load()
    share = product_share_data(request, produto, imagens_galeria, config, configuracao)
    context = {
        'product_share': share,
        'share_whatsapp_url': share['whatsapp_url'],
        'valor_sem_S': valor_br_semS,
        'valor_br': valor_br,
        'produto': produto,
        'imagens_galeria': imagens_galeria,
        'categorias': categorias,
        'cart_count': cart_count,
        'tot_prod_cart': len(cart),
        'color_theme': config.color_theme if config else '#ff5900',
        'config': config,
        'configuracao': configuracao,
    }

    return render(request, 'loja/produto/detail.html', context)


# Envio do formulário de suporte (modal "Suporte") ============================
@require_POST
def loja_ai_chat(request):
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Mensagem inválida.'}, status=400)

    message = str(payload.get('message', '')).strip()
    session_id = str(payload.get('session_id') or '').strip() or str(request.session.session_key or 'default')
    if not message:
        return JsonResponse({'status': 'error', 'message': 'Digite uma mensagem.'}, status=400)

    if len(message) > 1000:
        return JsonResponse({'status': 'error', 'message': 'Mensagem muito longa.'}, status=400)

    tenant_id = getattr(getattr(request, 'tenant', None), 'id', None)
    state = ensure_chat_session_state(session_id, tenant_id=tenant_id)
    state = reset_idle_operator_session(session_id, tenant_id=tenant_id) or state
    if tenant_id is not None and not chat_session_belongs_to_tenant(session_id, tenant_id):
        return JsonResponse({'status': 'error', 'message': 'Sessão de chat inválida.'}, status=403)

    if state['mode'] == 'closed':
        return JsonResponse({'status': 'error', 'mode': 'closed', 'message': 'Esta sessão foi encerrada. Recarregue a página para iniciar outra conversa.'}, status=409)

    customer_message = add_chat_message(session_id, 'customer', message, tenant_id=tenant_id)
    if state.get('mode') == 'operator':
        return JsonResponse({
            'status': 'ok',
            'answer': None,
            'ai_enabled': False,
            'handoff': True,
            'mode': 'operator',
            'session_id': session_id,
            'customer_message_id': customer_message['id'],
        })

    context = build_store_context(request)
    from .models import ChatSession
    phone = ChatSession.objects.get(tenant_id=tenant_id, session_key=session_id).customer_phone
    if phone:
        context.setdefault('cliente', {})['telefone'] = phone
    products = matching_products(message, context)
    ai_enabled = False
    if products:
        answer = product_details_reply(products, context)
    else:
        answer = chat_introduction(session_id, message, tenant_id=tenant_id, context=context)
        if answer is None:
            answer, ai_enabled = ask_ai_assistant(message, context, tenant_id=tenant_id)
    bot_message = add_chat_message(session_id, 'bot', answer, tenant_id=tenant_id)

    return JsonResponse({
        'status': 'ok',
        'answer': answer,
        'ai_enabled': ai_enabled,
        'handoff': bool(state.get('mode') == 'operator'),
        'mode': state.get('mode', 'bot'),
        'session_id': session_id,
        'customer_message_id': customer_message['id'],
        'answer_message_id': bot_message['id'],
    })


def loja_ai_chat_status(request):
    session_id = str(request.GET.get('session_id') or request.POST.get('session_id') or '').strip() or str(request.session.session_key or 'default')
    tenant_id = getattr(getattr(request, 'tenant', None), 'id', None)
    create_session = str(request.GET.get('create') or request.POST.get('create') or '').lower() in ('1', 'true', 'yes')
    if create_session:
        state = ensure_chat_session_state(session_id, tenant_id=tenant_id)
    else:
        state = get_chat_session(session_id, tenant_id=tenant_id)

    if state is None:
        return JsonResponse({
            'status': 'ok',
            'introduction_complete': False,
            'handoff': False,
            'mode': 'bot',
            'session_id': session_id,
            'exists': False,
        })

    return JsonResponse({
        'status': 'ok',
        'introduction_complete': state['introduction_complete'],
        'handoff': state.get('mode') == 'operator',
        'mode': state.get('mode', 'bot'),
        'session_id': session_id,
        'exists': True,
    })


def loja_ai_chat_messages(request):
    session_id = str(request.GET.get('session_id') or '').strip() or str(request.session.session_key or 'default')
    tenant_id = getattr(getattr(request, 'tenant', None), 'id', None)
    if not chat_session_belongs_to_tenant(session_id, tenant_id):
        return JsonResponse({'status': 'error', 'message': 'Sessão de chat inválida.'}, status=403)

    try:
        after_id = max(0, int(request.GET.get('after_id', 0)))
    except (TypeError, ValueError):
        after_id = 0
    return JsonResponse({
        'status': 'ok',
        'messages': get_chat_messages(session_id, after_id, tenant_id=tenant_id),
    })


@require_POST
def loja_ai_chat_assumir(request):
    if not getattr(request.user, 'is_staff', False):
        return JsonResponse({'status': 'error', 'message': 'Acesso restrito ao operador.'}, status=403)

    session_id = str(request.POST.get('session_id') or '').strip() or str(request.session.session_key or 'default')
    action = str(request.POST.get('action', 'assumir')).strip().lower()
    tenant_id = getattr(request.user, 'tenant_id', None)
    if tenant_id != getattr(request.tenant, 'id', None) or not chat_session_belongs_to_tenant(session_id, tenant_id):
        return JsonResponse({'status': 'error', 'message': 'Sessão de chat inválida.'}, status=403)
    state = set_chat_session_mode(session_id, 'bot' if action == 'liberar' else 'operator', request.user.id, tenant_id=tenant_id)
    return JsonResponse({
        'status': 'ok',
        'mode': state.get('mode', 'bot'),
        'handoff': state.get('mode') == 'operator',
        'session_id': session_id,
        'assumido_por': state.get('assumido_por'),
    })


def enviar_suporte(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método não permitido.'}, status=405)

    nome = request.POST.get('nome', '').strip()
    email = request.POST.get('email', '').strip()
    assunto = request.POST.get('assunto', '').strip()

    if not nome or not email or not assunto:
        return JsonResponse({'status': 'error', 'message': 'Preencha nome, e-mail e assunto.'}, status=400)

    config = TenantSettings.objects.filter(tenant=request.tenant).first()
    destinatario = config.support_email if config and config.support_email else None

    if not destinatario:
        return JsonResponse({'status': 'error', 'message': 'E-mail de suporte não configurado para esta loja.'}, status=400)

    # Reutiliza a mesma ferramenta de envio de e-mails usada na recuperação de senha
    send_mail(
        subject=f'[Suporte] {assunto}',
        message=f'Nome: {nome}\nE-mail: {email}\n\nAssunto:\n{assunto}',
        from_email=None,
        recipient_list=[destinatario],
    )

    return JsonResponse({'status': 'ok'})



# Adicionar produto ao carrinho ===============================================
def add_to_cart(request):
        
    # Só aceita POST
    if request.method == 'POST':
        
        produto_id = request.POST.get('produto_id')
        quantidade = int(request.POST.get('quantidade', 1))

        # Pega o carrinho da sessão
        cart = cart = get_cart(request)

        # Adiciona ou atualiza quantidade
        if produto_id in cart:
            cart[produto_id] += quantidade
        else:
            cart[produto_id] = quantidade

        # Salva carrinho na sessão
        request.session['cart'] = cart
        request.session.modified = True

        # Debug: imprime tudo do carrinho
        print("=== DEBUG CARRINHO ===")
        #print(request.session.get('cart', {}))
        print(cart)

        for pid, qty in cart.items():
            try:
                produto = Produto.objects.get(id=pid)
                print(f"Produto: {produto.nome} (ID: {pid}), Quantidade: {qty}, Subtotal: R${produto.price * qty:.2f}")
            except Produto.DoesNotExist:
                print(f"Produto ID {pid} não existe mais! Quantidade: {qty}")
        print("=======================")

        # Retorna info do produto e total
        produto = Produto.objects.get(id=produto_id)
        subtotal = produto.price * cart[produto_id]

        qtd_pedidos = len(cart)         

        return JsonResponse({
            'status': 'ok',
            'produto': {
                'id': produto.id,
                'nome': produto.nome,
                'quantidade': cart[produto_id],
                'subtotal': f"{subtotal:.2f}"
            },
            'cart_count': sum(cart.values()),
            'qtd_pedidos' : qtd_pedidos
        })
    return JsonResponse({'status': 'error'}, status=400)


# Remover produto do carrinho ================================================

def remover_do_carrinho_ajax(request):
    if request.method == "POST":
        produto_id = request.POST.get("produto_id")
        carrinho = request.session.get("cart", {})

        if str(produto_id) in carrinho:
            del carrinho[str(produto_id)]
            request.session["cart"] = carrinho
            request.session.modified = True

        # Recalcula total do carrinho
        total = 0
        for pid, qtd in carrinho.items():
            p = get_object_or_404(Produto, id=pid)
            total += p.price * qtd

        return JsonResponse({
            "status": "ok",
            "cart_count": sum(carrinho.values()),
            "total": total
        })

    return JsonResponse({"status": "erro", "mensagem": "Requisição inválida."})

# Ver carrinho ================================================================
def sacola(request):
    cart = get_cart(request)
    cart_count = sum(cart.values())
    produtos = []
    total = 0
    for produto_id, qtd in cart.items():
        produto = get_object_or_404(Produto, id=produto_id)
        subtotal = produto.price * qtd
        total += subtotal
        produtos.append({
            'produto': produto,
            'quantidade': qtd,
            'subtotal': subtotal,
        })

    categorias = get_categorias(request)
    settings = TenantSettings.load(tenant=request.tenant)

    context = {
        'produtos': produtos,
        'total': formatar_brl(total),
        'categorias': categorias,
        'cart_count': cart_count,
        'color_theme': settings.color_theme or '#ff5900',
        'config': settings,
    }

    return render(request, 'loja/sacola.html', context)




def atualizar_carrinho_ajax(request):
    if request.method == "POST" and request.headers.get("x-requested-with") == "XMLHttpRequest":
        produto_id = request.POST.get("produto_id")
        quantidade = request.POST.get("quantidade")

        try:
            quantidade = int(quantidade)
            produto = get_object_or_404(Produto, id=produto_id)
        except (ValueError, Produto.DoesNotExist):
            return JsonResponse({"status": "erro", "mensagem": "Produto inválido."})

        # Recupera carrinho da sessão
        carrinho = request.session.get("cart", {})

        if quantidade < 1:
            # Remove produto do carrinho se quantidade for menor que 1
            carrinho.pop(str(produto_id), None)
        else:
            # Atualiza quantidade
            carrinho[str(produto_id)] = quantidade

        request.session["cart"] = carrinho
        request.session.modified = True

        # Calcula subtotal do item e total do carrinho
        item_subtotal = produto.price * quantidade if quantidade > 0 else 0
        total = sum(get_object_or_404(Produto, id=pid).price * qtd for pid, qtd in carrinho.items())

        return JsonResponse({
            "status": "ok",
            "cart_count": sum(carrinho.values()),
            "item_subtotal": item_subtotal,
            "total": total
        })

    return JsonResponse({"status": "erro", "mensagem": "Requisição inválida."})


# Checkout ===================================================================
@transaction.atomic
def checkout(request):
    if request.method == 'POST':
        tenant = getattr(request, 'tenant', None)
        if tenant is None:
            return JsonResponse({'status': 'error', 'message': 'Loja não identificada.'}, status=400)
        cart = get_cart(request)

        if not cart:
            return JsonResponse({'status': 'error', 'message': 'Carrinho vazio'}, status=400)

        if any(type(qty) is not int or qty < 1 for qty in cart.values()):
            return JsonResponse({'status': 'error', 'message': 'Quantidade inválida.'}, status=400)
        # Criar ordem temporária
        ordem = Ordem.objects.create(
            tenant=tenant,
            transacao_id=str(uuid.uuid4())[:8]
        )

        for produto_id, qtd in cart.items():
            produto = get_object_or_404(Produto, id=produto_id, tenant=tenant)
            OrdemItem.objects.create(
                tenant=tenant,
                ordem=ordem,
                produto=produto,
                quantidade=qtd,
                preco_unitario=produto.price,
            )

        ordem.valor_total = ordem.get_car_total
        ordem.save(update_fields=['valor_total'])

        # Limpa o carrinho da sessão
        save_cart(request, {})

        return JsonResponse({'status': 'ok', 'ordem_id': ordem.id})
    
    # Se for GET, mostrar formulário de checkout (nome, email, endereço)
    return render(request, 'loja/checkout.html')

# Pedido Delivery ##########################################################



from django.utils.html import escape
import urllib.parse

def checkout_sucesso(request):
    # Recupera dados do último pedido salvo na sessão (ou personalize conforme sua lógica)
    pedido_info = request.session.get('last_pedido_info')
    if not pedido_info:
        return HttpResponse("<h1>Pedido finalizado</h1><p>Não foi possível montar o link do WhatsApp.</p>")

    if not Ordem.objects.filter(pk=pedido_info.get('pedido_id'), tenant=request.tenant).exists():
        return HttpResponse('Pedido não encontrado nesta loja.', status=404)
    config = TenantSettings.load(tenant=request.tenant)

    vendedor = pedido_info.get('vendedor', '') or 'Não informado'
    mensagem_linhas = [
        'NOVO PEDIDO',
        f"Loja: {pedido_info.get('loja', '')}",
        f"Pedido: {pedido_info.get('pedido_id', '')}",
        f"Data: {pedido_info.get('datahora', '')}",
        '',
        'CLIENTE',
        f"Nome: {pedido_info.get('nome', '')}",
        f"WhatsApp: {pedido_info.get('whatsapp', '') or 'Não informado'}",
        f"Vendedor: {vendedor}",
    ]
    endereco = ', '.join(filter(None, [
        f"CEP {pedido_info.get('cep', '')}" if pedido_info.get('cep') else '',
        f"Bairro {pedido_info.get('bairro', '')}" if pedido_info.get('bairro') else '',
        f"Rua {pedido_info.get('rua', '')}" if pedido_info.get('rua') else '',
        f"Complemento {pedido_info.get('complemento', '')}" if pedido_info.get('complemento') else '',
        f"Referência {pedido_info.get('referencia', '')}" if pedido_info.get('referencia') else '',
    ]))
    if endereco:
        mensagem_linhas.extend(['', 'ENDEREÇO', endereco])
    mensagem_linhas.extend(['', 'PRODUTOS'])
    for item in pedido_info.get('produtos', []):
        mensagem_linhas.extend([
            f"{item['quantidade']} x {item['nome']} (ref. {item.get('referencia', '')})",
            f"Preço: R$ {item.get('preco', item['valor']):.2f}",
            f"Subtotal: R$ {item['valor']:.2f}",
            f"Descrição: {item.get('descricao', '') or 'Não informada'}",
            f"Foto: {item.get('imagem', '') or 'Não disponível'}",
            f"Produto: {item.get('link', '') or 'Não disponível'}",
            '',
        ])
    loja_url = get_tenant_url(request, '/loja/')
    mensagem_linhas.extend([
        f"Subtotal geral: R$ {pedido_info.get('subtotal', 0):.2f}",
        f"Entrega: {pedido_info.get('entrega', '') or 'A combinar'}",
        f"Forma de pagamento: {pedido_info.get('pagamento', '') or 'A combinar'}",
        f"Total: R$ {pedido_info.get('total', 0):.2f}",
        '',
        f"Loja: {loja_url}",
    ])
    mensagem = '\n'.join(mensagem_linhas)

    mensagem_url = urllib.parse.quote(mensagem)
    telefone = re.sub(r'\D', '', str(pedido_info.get('telefone_loja', '') or ''))
    if len(telefone) in (10, 11) and not telefone.startswith('55'):
        telefone = f'55{telefone}'

    if not telefone:
        return HttpResponse('<h1>Pedido registrado</h1><p>O WhatsApp da loja ainda não está cadastrado na etapa 5 de Configurações.</p>')

    link_whatsapp = f"https://api.whatsapp.com/send/?phone={telefone}&text={mensagem_url}&type=phone_number&app_absent=0"

    html = f"""
    <html><head>
    <meta http-equiv='refresh' content='5;url={link_whatsapp}' />
    <style>body{{text-align:center;font-family:sans-serif;}}</style>
    </head><body>
    <h1>Pedido finalizado com sucesso!</h1>
    <p>Você será redirecionado para o WhatsApp em 5 segundos...</p>
    <a href='{link_whatsapp}' target='_blank'>Clique aqui se não for redirecionado automaticamente</a>
    </body></html>
    """
    return HttpResponse(html)


def manifest_json(request):
    """
    Serve o arquivo manifest.json para PWA
    """
    import json
    from django.http import JsonResponse
    
    # Pega informações do tenant se existir
    nome_loja = "Burger App"
    if hasattr(request, 'tenant') and request.tenant:
        try:
            config = TenantSettings.objects.get(tenant=request.tenant)
            nome_loja = config.nome_loja
        except TenantSettings.DoesNotExist:
            pass
    
    manifest = {
        "background_color": "#ff5900",
        "description": f"{nome_loja} - Delivery de Hambúrgueres",
        "display": "standalone",
        "icons": [
            {
                "src": "/static/_core/_uploads/cadastro/2023/02/20061802236e3jji4ffg_thumb.jpg",
                "sizes": "192x192",
                "type": "image/jpeg"
            },
            {
                "src": "/static/_core/_uploads/cadastro/2023/02/20061802236e3jji4ffg_thumb.jpg",
                "sizes": "512x512",
                "type": "image/jpeg"
            }
        ],
        "name": nome_loja,
        "short_name": nome_loja,
        "start_url": "/",
        "theme_color": "#ff5900",
        "scope": "/"
    }
    
    return JsonResponse(manifest, content_type='application/manifest+json')


@csrf_exempt
def cloudflare_dummy(request, path=""):
    """
    Retorna resposta vazia para requests do Cloudflare que não existem localmente
    """
    if 'email-decode' in request.path:
        # Retorna um script vazio para email-decode.min.js
        return HttpResponse("// Email protection script not needed in development", content_type='application/javascript')
    elif 'rum' in request.path:
        # Para RUM (Real User Monitoring), retorna sucesso para POST/GET
        if request.method == 'POST':
            # Retorna JSON vazio para simular resposta do RUM
            return JsonResponse({'status': 'ok'}, status=200)
        else:
            # Retorna script vazio para GET
            return HttpResponse("// RUM script not needed in development", content_type='application/javascript')
    else:
        # Para outras requisições CDN, retorna 204 No Content
        return HttpResponse(status=204)


def image_placeholder(request):
    """
    Gera um placeholder de imagem dinâmico quando a imagem não existe
    """
    # Cria uma imagem 40x40 cinza
    width, height = 40, 40
    background_color = (240, 240, 240)  # Cinza claro
    text_color = (150, 150, 150)  # Cinza escuro
    
    # muda a cor de fundo se a configuração de adicionar ruído estiver ativada
    if settings.ADICIONAR_RUIDO_EM_FOTOS:
        background_color = (200, 200, 200)  # Cinza um pouco mais escuro
   
    img = Image.new('RGB', (width, height), background_color)
    draw = ImageDraw.Draw(img)
    
    # Adiciona um ícone simples (quadrado com "?")
    draw.rectangle([8, 8, 32, 32], outline=text_color, width=2)
    try:
        # Tenta usar uma fonte do sistema
        font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSans.ttf", 14)
    except:
        # Usa fonte padrão se não encontrar
        font = ImageFont.load_default()
    
    # Adiciona o texto "?" no centro
    bbox = draw.textbbox((0, 0), "?", font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    draw.text((x, y), "?", fill=text_color, font=font)
    
    # Converte para bytes
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return HttpResponse(buffer.getvalue(), content_type='image/png')
