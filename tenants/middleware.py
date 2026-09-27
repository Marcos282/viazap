import logging
from typing import Iterable

import tldextract
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from .models import Tenant


logger = logging.getLogger(__name__)


def _default_allowed_subdomains() -> Iterable[str]:
    return (
        "www",
        "admin",
        "api",
        "static",
        "media",
        "localhost",
        "lignetbrasil",
        "lignetbrasil.com.br",
        "lignetbrasil.com",
        "burger",
        "burger.com.br",
        "burger.com",
    )


class TenantMiddleware:
    """
    Resolve a Tenant from the request host subdomain.

    Behavior:
    - Normalizes host (removes port, trailing dots, lowercases).
    - Uses settings.TENANT_ALLOWED_SUBDOMAINS when present, otherwise a sensible default.
    - Sets `request.tenant` to a Tenant instance or None.
    - Raises Http404 when a non-allowed subdomain has no Tenant.
    - If downstream returns None (incorrectly), redirects to `home_view` to avoid middleware errors.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    PANEL_PREFIXES = (
        "/painel/",
        "/painel",
    )

    # Domínios de túnel de teste (ngrok, cloudflare, etc.): tratados sempre como site principal,
    # pois o "subdomínio" nesses hosts é um identificador de sessão do túnel, não um tenant.
    TUNNEL_REGISTERED_DOMAINS = {
        "ngrok-free.dev",
        "ngrok.app",
        "ngrok.io",
        "ngrok-free.app",
        "trycloudflare.com",
        "loca.lt",
    }

    def __call__(self, request):
        # Normalize host and extract subdomain
        host = (request.get_host() or "").split(":")[0].strip().lower().strip(".")
        if host.endswith(".localhost"):
            # tldextract trata localhost como domínio sem registro e perde o prefixo.
            subdomain = host[: -len(".localhost")]
            registered_domain = "localhost"
        else:
            try:
                extracted = tldextract.extract(host)
                subdomain = (extracted.subdomain or "").lower()
                registered_domain = extracted.registered_domain.lower()
            except Exception:
                logger.exception("Erro ao extrair subdomínio do host: %s", host)
                subdomain = ""
                registered_domain = ""

        if registered_domain in self.TUNNEL_REGISTERED_DOMAINS:
            logger.debug("Host de túnel de teste detectado (%s); ignorando subdomínio.", host)
            subdomain = ""

        # Prepare allowed subdomains (configurable)
        allowed = getattr(settings, "TENANT_ALLOWED_SUBDOMAINS", None)
        if allowed is None:
            allowed = set(_default_allowed_subdomains())
        else:
            allowed = set(str(x).lower() for x in allowed)

        # Default values
        request.tenant = None
        tenant_id = 0

        # Resolve tenant when appropriate
        if subdomain:
            logger.debug("Subdomínio detectado: %s", subdomain)
            if subdomain in allowed:
                logger.debug("Subdomínio '%s' está na lista de liberados", subdomain)
                request.tenant = None
            else:
                try:
                    tenant = Tenant.objects.get(subdomain=subdomain)
                    request.tenant = tenant
                    tenant_id = tenant.id
                    logger.info("✅ Tenant encontrado: %s | ID: %s", tenant, tenant_id)
                except Tenant.DoesNotExist:
                    logger.warning(
                        "⚠️ Tenant '%s' NÃO encontrado para path %s", subdomain, request.path
                    )
                    request.tenant = None
                    # If subdomain is not allowed, block access
                    if subdomain not in allowed:
                        raise Http404("Tenant não encontrado")
        else:
            logger.info("ℹ️ Sem subdomínio (site principal)")

        if request.tenant is not None and request.path == '/' and request.method in ('GET', 'HEAD'):
            return redirect('/loja/')

        if self._authenticated_panel_user_on_wrong_tenant(request):
            logger.warning(
                "Bloqueando acesso ao painel: usuário tenant=%s em host tenant=%s path=%s",
                getattr(request.user, "tenant_id", None),
                getattr(request.tenant, "id", None),
                request.path,
            )
            logout(request)
            if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.path.endswith("/dados/") or request.path.endswith("/pendentes-count/"):
                return JsonResponse(
                    {"detail": "Acesso negado. Entre com a conta da loja deste endereço."},
                    status=403,
                )
            messages.error(request, "Entre com a conta da loja deste endereço.")
            return redirect("login")

        # Continue processing
        response = self.get_response(request)

        if request.user.is_authenticated:
            tenant_do_login = getattr(request.user, 'tenant', None)
            if tenant_do_login is not None:
                print("=== TENANT NO FINAL DO MIDDLEWARE ===")
                print({
                    'request_user': getattr(request.user, 'email', None),
                    'tenant_id': tenant_do_login.id,
                    'tenant_name': tenant_do_login.name,
                    'tenant_subdomain': tenant_do_login.subdomain,
                    'session_tenant_id': request.session.get('tenant_id'),
                    'session_id_tenant': request.session.get('id_tenant'),
                })
                print("====================================")

        # Guard: if downstream mistakenly returned None, redirect to home_view
        if response is None:
            logger.warning("⚠️ get_response retornou None; redirecionando para home_view")
            try:
                home_path = reverse("home_view")
            except Exception:
                home_path = "/home_view/"

            if request.path != home_path:
                return redirect("home_view")

        return response

    def _authenticated_panel_user_on_wrong_tenant(self, request):
        if not request.path.startswith(self.PANEL_PREFIXES):
            return False

        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return False

        host_tenant = getattr(request, "tenant", None)
        user_tenant_id = getattr(user, "tenant_id", None)
        return host_tenant is not None and host_tenant.id != user_tenant_id


class RootStoreRedirectMiddleware:
    """Redireciona a raiz de subdomínios de lojas para /loja/."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = (request.get_host() or "").split(":")[0].strip().lower().strip(".")
        user = getattr(request, "user", None)
        host_tenant = getattr(request, "tenant", None)
        user_tenant_id = getattr(user, "tenant_id", None)

        if (
            request.method == "GET"
            and request.path == "/"
            and (host_tenant is not None or host.endswith(".localhost"))
        ):
            if host_tenant is None:
                raise Http404("Tenant não cadastrado")
            if host_tenant.id != user_tenant_id:
                if getattr(user, "is_authenticated", False):
                    raise Http404("Usuário não pertence a este tenant")
            return redirect("/loja/")

        return self.get_response(request)
