from django.utils import timezone
from django.conf import settings
from datetime import timedelta


def normalizar_datetime(valor):
    if valor is not None and timezone.is_naive(valor):
        return timezone.make_aware(valor, timezone.get_current_timezone())
    return valor


def calcular_dias_restantes(data_expiracao, agora=None):
    data_expiracao = normalizar_datetime(data_expiracao)
    agora = normalizar_datetime(agora or timezone.now())
    return (data_expiracao - agora).days


def gravar_os_dias(dias_restantes, data_atual=None, dias=30):
    """Retorna a nova expiração, já com timezone, após creditar ``dias``.

    ``dias_restantes`` pode ser um número de dias ou um ``timedelta``. Valores
    positivos são preservados e recebem o novo crédito; valores zero ou
    negativos iniciam o prazo com apenas os dias do crédito.
    """
    data_atual = normalizar_datetime(data_atual or timezone.now())

    if isinstance(dias_restantes, timedelta):
        restante = max(dias_restantes, timedelta())
    else:
        restante = timedelta(days=max(dias_restantes or 0, 0))

    return data_atual + restante + timedelta(days=dias)


def somar_data_expiracao(user, dias_creditados=30):
    """Consulta a data de expiração do usuário no banco de dados,
    soma os dias creditados (preservando os dias restantes) e
    retorna a nova data com timezone pronta para salvar.
    """
    agora = timezone.now()
    if getattr(user, 'pk', None):
        user.refresh_from_db(fields=['data_expiracao'])

    expiracao_atual = normalizar_datetime(user.data_expiracao)
    base = expiracao_atual if (expiracao_atual and expiracao_atual > agora) else agora
    return base + timedelta(days=dias_creditados)


def estender_expiracao(user, dias=30):
    """Calcula a nova expiração e salva no banco de dados."""
    user.data_expiracao = somar_data_expiracao(user, dias)
    user.save(update_fields=['data_expiracao'])
    return user.data_expiracao
def formatar_brl(valor):
    return f"R$ {valor:,.2f}".replace('.', ',')

def formatar_brl_noS(valor):
    return f"{valor:,.2f}".replace('.', ',')

def formatar_brl_to_float(valor_str):
    try:
        valor_str = valor_str.replace('R$', '').replace('.', '').replace(',', '.').strip()
        return float(valor_str)
    except ValueError:
        return 0.0


def build_public_url(request, path=''):
    """Monta links públicos usando o domínio configurado em produção."""
    from django.conf import settings

    if settings.PUBLIC_SITE_URL:
        return f'{settings.PUBLIC_SITE_URL}/{path.lstrip("/")}'
    return request.build_absolute_uri(path)

def build_full_url(request, path='', user=None):
    """
    Constrói uma URL completa incluindo o subdomínio do tenant
    
    Args:
        request: HttpRequest object
        path: Caminho relativo (opcional)
        user: User object (opcional, se não fornecido usa request.user)
    
    Returns:
        str: URL completa com subdomínio do tenant
    """
    from tenants.models import Configuracao, Tenant

    config = Configuracao.load()
    domain = (config.dominio or '').strip().removeprefix('https://').removeprefix('http://').rstrip('/')

    # Determina qual user usar
    target_user = user if user else getattr(request, 'user', None)
    tenant = getattr(request, 'tenant', None)

    if tenant is None and target_user and getattr(target_user, 'is_authenticated', False):
        try:
            tenant = getattr(target_user, 'tenant', None)
        except Exception:
            tenant = None

    if tenant is None and hasattr(request, 'session'):
        tenant_id = request.session.get('tenant_id') or request.session.get('id_tenant')
        if tenant_id:
            tenant = Tenant.objects.filter(id=tenant_id).first()

    # Pega subdomínio do tenant ou da sessão
    subdomain = None
    if tenant:
        subdomain = tenant.subdomain
    elif hasattr(request, 'session') and request.session.get('tenant_subdomain'):
        subdomain = request.session.get('tenant_subdomain')

    # Remove a barra inicial do path se existir para evitar duplicação
    if path.startswith('/'):
        path = path[1:]

    # Obtém o subdomínio e domínio
    if subdomain:
        if domain:
            protocol = 'http' if domain.startswith(('localhost', '127.0.0.1')) else 'https'
            host = f"{subdomain}.{domain}"
        else:
            protocol = 'http' if settings.DEBUG else ('https' if request.is_secure() else 'http')
            host = f"{subdomain}.localhost:8000" if settings.DEBUG else request.get_host()
    else:
        protocol = 'http' if (domain and domain.startswith(('localhost', '127.0.0.1'))) else ('https' if domain else ('http' if settings.DEBUG else 'https'))
        host = domain if domain else request.get_host()
    
    # Constrói a URL completa
    full_url = f"{protocol}://{host}/{path}"
    
    return full_url

def get_tenant_url(request, path='', user=None):
    """
    Alias para build_full_url com foco no tenant (mantido para compatibilidade)
    
    Args:
        request: HttpRequest object  
        path: Caminho relativo (opcional)
        user: User object (opcional, se não fornecido usa request.user)
    
    Returns:
        str: URL completa com subdomínio do tenant
    """
    return build_full_url(request, path, user)

def build_tenant_url_for_user(user, path='', protocol='http', domain='localhost:8000'):
    """
    Constrói URL completa para um usuário específico (útil para emails, notificações, etc.)
    
    Args:
        user: User object
        path: Caminho relativo (opcional)
        protocol: 'http' ou 'https' (padrão: 'http')
        domain: Domínio base (padrão: 'localhost:8000')
    
    Returns:
        str: URL completa com subdomínio do tenant
    
    Exemplo:
        build_tenant_url_for_user(user, '/produto/123/', 'https', 'meusite.com')
        # Retorna: https://marcos.meusite.com/produto/123/
    """
    if user and hasattr(user, 'tenant') and user.tenant:
        subdomain = user.tenant.subdomain
        
        # Remove protocolo do domain se existir
        if domain.startswith(('http://', 'https://')):
            domain = domain.split('://', 1)[1]
        
        host = f"{subdomain}.{domain}"
    else:
        # Fallback sem subdomínio
        host = domain
    
    # Remove a barra inicial do path se existir
    if path.startswith('/'):
        path = path[1:]
    
    return f"{protocol}://{host}/{path}"


def verificar_loja_aberta(request, user=None):
    """
    Função utilitária para verificar se a loja está aberta.
    
    Args:
        request: HttpRequest object
        user: User object (opcional, se não fornecido usa request.user)
    
    Returns:
        dict: {
            'aberta': bool,
            'status_texto': str,
            'proximo_evento': dict ou None,
            'horarios_hoje': QuerySet
        }
    """
    from datetime import datetime, timedelta
    
    # Determina qual tenant usar - prioriza request.tenant (multi-tenant) sobre user.tenant
    tenant = None
    if hasattr(request, 'tenant') and request.tenant:
        tenant = request.tenant
    else:
        target_user = user if user else getattr(request, 'user', None)
        if target_user and hasattr(target_user, 'tenant') and target_user.tenant:
            tenant = target_user.tenant
    
    if not tenant:
        return {
            'aberta': False,
            'status_texto': 'Loja não configurada',
            'proximo_evento': None,
            'horarios_hoje': None,
            'is_open': False,
        }
    
    agora = datetime.now()
    
    # DEBUG: Adicionar logs detalhados
    print(f"=== DEBUG VERIFICAR_LOJA_ABERTA ===")
    print(f"Tenant: {tenant.name}")
    print(f"Data/Hora atual: {agora}")
    print(f"Dia da semana: {agora.weekday()} (0=segunda, 6=domingo)")
    print(f"Hora atual: {agora.time()}")
    
    # Verificar horários cadastrados
    from tenants.models import HorarioFuncionamento
    todos_horarios = HorarioFuncionamento.objects.filter(tenant=tenant)
    print(f"Total de horários cadastrados: {todos_horarios.count()}")
    
    for h in todos_horarios:
        print(f"  - Dia {h.dia_semana} ({h.get_dia_semana_display()}): {h.horario_abre}-{h.horario_fecha}, Ativo: {h.ativo}, Data específica: {h.data_especifica}")
    
    # Verificar horários para hoje
    horarios_hoje = tenant.get_horarios_hoje(agora)
    print(f"Horários para hoje: {horarios_hoje.count()}")
    for h in horarios_hoje:
        print(f"  - {h.horario_abre}-{h.horario_fecha}, Ativo: {h.ativo}")
    
    esta_aberta = tenant.esta_aberto_agora(agora)
    print(f"Resultado esta_aberto_agora: {esta_aberta}")
    
    proximo_evento = tenant.get_proximo_horario(agora)
    print(f"Próximo evento: {proximo_evento}")
    
    if esta_aberta:
        is_open = True
        status_texto = "🟢 ABERTA"
        if proximo_evento and proximo_evento['acao'] == 'fecha':
            horario_str = proximo_evento['horario'].strftime('%H:%M')
            if proximo_evento['data'] == agora.date():
                status_texto += f" - Fecha às {horario_str}"
            else:
                status_texto += f" - Fecha amanhã às {horario_str}"
    else:
        is_open = False
        status_texto = "🔴 FECHADA"
        if proximo_evento and proximo_evento['acao'] == 'abre':
            horario_str = proximo_evento['horario'].strftime('%H:%M')
            if proximo_evento['data'] == agora.date():
                status_texto += f" - Abre às {horario_str}"
            elif proximo_evento['data'] == agora.date() + timedelta(days=1):
                status_texto += f" - Abre amanhã às {horario_str}"
            else:
                dia_nome = [
                    'Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'
                ][proximo_evento['data'].weekday()]
                status_texto += f" - Abre {dia_nome} às {horario_str}"
    
    return {
        'aberta': esta_aberta,
        'status_texto': status_texto,
        'proximo_evento': proximo_evento,
        'horarios_hoje': horarios_hoje,
        'is_open': is_open,
    }


def product_share_data(request, produto, imagens_galeria, config, configuracao):
    """Dados públicos de compartilhamento; receber produto filtrado pelo tenant."""
    from html import unescape
    from urllib.parse import urlencode, urlsplit, urlunsplit
    from django.templatetags.static import static
    from django.urls import reverse
    from django.utils.html import strip_tags
    from django.utils.text import Truncator

    def clean(value):
        return ' '.join(strip_tags(unescape(value or '')).split())

    def https_url(path):
        parts = urlsplit(request.build_absolute_uri(path))
        return urlunsplit(parts._replace(scheme='https', fragment=''))

    title = clean(produto.nome)
    price = f"R$ {produto.price:,.2f}".translate(str.maketrans(',.', '.,'))
    description = clean(produto.description) or title
    description = f'{Truncator(description).chars(180)} — {price}.'
    image = produto.image or next((item.imagem for item in imagens_galeria if item.imagem), None) or produto.imagem_extra
    image_path = image.url if image else None
    if not image_path and config:
        image_path = config.foto_perfil.url if config.foto_perfil else config.logo_url
    if not image_path:
        image_path = configuracao.logo.url if configuracao.logo else static('_core/_uploads/cadastro/2023/02/20061802236e3jji4ffg_thumb.jpg')
    url = https_url(reverse('detalhe', args=[produto.pk]))
    text = f'Olha esse produto 👇\n\n{title}\n{price}\n\n{url}'
    return {
        'title': title, 'description': description, 'text': text,
        'native_text': f'{title} — {price}',
        'url': url, 'image': https_url(image_path), 'site_name': request.tenant.name,
        'whatsapp_url': 'https://api.whatsapp.com/send?' + urlencode({'text': text}),
    }


def store_share_data(request, tenant, config, configuracao):
    """Preview público da loja, compartilhado pelo painel e pela vitrine."""
    from html import unescape
    from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
    from django.templatetags.static import static
    from django.urls import reverse
    from django.utils.html import strip_tags
    from django.utils.text import Truncator

    title = tenant.name
    description = (config.descricao_loja if config else '') or f'Conheça os produtos da {title}.'
    description = Truncator(' '.join(strip_tags(unescape(description)).split())).chars(180)
    if getattr(request, 'tenant', None) == tenant:
        url = request.build_absolute_uri(reverse('loja'))
    else:
        url = get_tenant_url(request, reverse('loja'))
    url = urlunsplit(urlsplit(url)._replace(scheme='https', query='', fragment=''))
    image = None
    if config:
        image = config.foto_perfil.url if config.foto_perfil else config.logo_url
    if not image:
        image = configuracao.logo.url if configuracao.logo else static('_core/_uploads/cadastro/2023/02/20061802236e3jji4ffg_thumb.jpg')
    image = urlunsplit(urlsplit(urljoin(url, image))._replace(scheme='https'))
    text = f'{title}\n\n{description}\n\n{url}'
    return {'title': title, 'description': description, 'image': image, 'url': url,
            'whatsapp_url': 'https://wa.me/?' + urlencode({'text': text})}
