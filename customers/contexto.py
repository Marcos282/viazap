import re

from tenants.models import Tenant, Configuracao, TenantSettings


def configuracao_context(request):
    """Expõe configurações gerais e o WhatsApp normalizado da loja."""
    tenant = getattr(request, 'tenant', None)
    loja_settings = TenantSettings.objects.filter(tenant=tenant).first() if tenant else None
    whatsapp_numero = re.sub(r'\D', '', loja_settings.whatsapp or '') if loja_settings else ''
    if len(whatsapp_numero) in (10, 11):
        whatsapp_numero = f'55{whatsapp_numero}'
    analytics_tag = (loja_settings.tag_google_analytics or '').strip().upper() if loja_settings else ''
    if not analytics_tag and loja_settings:
        analytics_tag = (loja_settings.googleanalytics or '').strip().upper()
    return {
        'configuracao': Configuracao.load(),
        'loja_whatsapp_numero': whatsapp_numero,
        'ga_measurement_id': analytics_tag if re.fullmatch(r'G-[A-Z0-9]+', analytics_tag) else '',
        'gtm_container_id': analytics_tag if re.fullmatch(r'GTM-[A-Z0-9]+', analytics_tag) else '',
    }


def loja_aberta_context(request):
    """Expõe o mesmo estado de abertura no painel e na loja pública."""
    user = getattr(request, 'user', None)
    tenant = getattr(request, 'tenant', None)
    if tenant is None and user and user.is_authenticated:
        tenant = getattr(user, 'tenant', None)
    if tenant is None:
        return {'loja_aberta': None}
    return {'loja_aberta': bool(TenantSettings.objects.filter(tenant=tenant).values_list('aberto', flat=True).first())}


def buscar_tenant_por_email(email):
    """Busca o tenant relacionado ao usuário autenticado pelo email."""
    if not email:
        return None

    try:
        from customers.models import User

        user = User.objects.filter(email=email).first()
        if user and getattr(user, 'tenant', None):
            return user.tenant
    except Exception:
        return None

    return None


def salvar_tenant_em_sessao(request, email=None, user=None):
    """Salva o tenant autenticado na sessão do usuário."""
    if not hasattr(request, 'session'):
        return None

    if user is None:
        user = getattr(request, 'user', None)

    if email is None and user is not None:
        email = getattr(user, 'email', None)

    tenant = None

    if email:
        tenant = buscar_tenant_por_email(email)

    if tenant is None and user is not None and getattr(user, 'is_authenticated', False):
        tenant = getattr(user, 'tenant', None)

    if tenant is None:
        tenant_id = request.session.get('tenant_id') or request.session.get('id_tenant')
        if tenant_id:
            tenant = Tenant.objects.filter(id=tenant_id).first()

    if tenant is not None:
        request.session['tenant_id'] = tenant.id
        request.session['id_tenant'] = tenant.id
        request.session['tenant_subdomain'] = tenant.subdomain
        request.session['tenant_nome'] = tenant.name
        request.session.modified = True
        request.tenant = tenant

        print("=== TENANT BUSCADO PELO LOGIN ===")
        print({
            'id': tenant.id,
            'name': tenant.name,
            'subdomain': tenant.subdomain,
            'email': email,
        })
        print("=== SESSION TENANT DEBUG ===")
        print({
            'tenant_id': request.session.get('tenant_id'),
            'id_tenant': request.session.get('id_tenant'),
            'tenant_subdomain': request.session.get('tenant_subdomain'),
            'tenant_nome': request.session.get('tenant_nome'),
        })
        print("===========================")
        return tenant

    return None


def recuperar_tenant_do_contexto(request):
    """Recupera o tenant da sessão e o expõe no contexto do template."""
    tenant = None
    tenant_id = request.session.get('tenant_id') if hasattr(request, 'session') else None

    if tenant_id is None and hasattr(request, 'session'):
        tenant_id = request.session.get('id_tenant')

    if tenant_id:
        tenant = Tenant.objects.filter(id=tenant_id).first()

    if tenant is None and getattr(request, 'user', None) is not None:
        tenant = getattr(request.user, 'tenant', None)

    if tenant is not None:
        request.tenant = tenant

    return {'tenant': tenant}

def url_marketplace_context(request):
    """Disponibiliza 'url_marketplace' globalmente em todos os templates."""
    from core.utils import get_tenant_url
    return {'url_marketplace': get_tenant_url(request, '/loja/')}


def dominio_full(request):
    """Retorna o domínio da loja com base na configuração."""
    config = Configuracao.load()
    domain = (config.dominio or '').strip().removeprefix('https://').removeprefix('http://').rstrip('/')
    subdomain = request.session.get('tenant_subdomain') if hasattr(request, 'session') else None
    if not subdomain:
        tenant = getattr(request, 'tenant', None) or getattr(getattr(request, 'user', None), 'tenant', None)
        subdomain = getattr(tenant, 'subdomain', None)

    protocol = 'http' if domain.startswith(('localhost', '127.0.0.1')) else 'https'
    if subdomain and domain:
        return f"{protocol}://{subdomain}.{domain}/loja/"
    elif domain:
        return f"{protocol}://{domain}/loja/"
    elif subdomain:
        return f"http://{subdomain}.localhost:8000/loja/"
    return f"https://{domain}/loja/" if domain else "http://localhost:8000/loja/"
