import logging
import tldextract
from .models import Tenant
from django.shortcuts import redirect
from django.urls import reverse
from django.conf import settings
from django.http import Http404

logger = logging.getLogger(__name__)

class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        logger.info("EXEMPLO_LOG_MIDDLEWARE: request recebida para %s", request.path)

        # 1. Extrai o subdomínio (normaliza host/porta)
        host = (request.get_host() or '').split(':')[0].strip().lower().strip('.')
        try:
            dados = tldextract.extract(host)
            subdominio = (dados.subdomain or '').lower()
        except Exception:
            logger.exception("Erro ao extrair subdomínio do host: %s", host)
            subdominio = ''

        nr = 0  # ✅ Definida AQUI (fora do if/else) → existe em todo lugar

        # Lista de subdomínios liberados — pode ser sobrescrita em settings
        allowed = getattr(settings, 'TENANT_ALLOWED_SUBDOMAINS', None)
        if allowed is None:
            allowed = {
                'www', 'admin', 'api', 'static', 'media', 'localhost',
                'lignetbrasil', 'lignetbrasil.com.br', 'lignetbrasil.com',
                'burger', 'burger.com.br', 'burger.com',
            }
        else:
            allowed = set(str(x).lower() for x in allowed)

        if subdominio:
            logger.debug("Subdomínio detectado: %s", subdominio)
            if subdominio in allowed:
                logger.debug("Subdomínio '%s' está na lista de liberados", subdominio)
                request.tenant = None
            else:
                try:
                    tenant = Tenant.objects.get(subdomain=subdominio)
                    request.tenant = tenant
                    nr = tenant.id
                    logger.info("✅ Tenant encontrado: %s | ID: %s", tenant, nr)
                except Tenant.DoesNotExist:
                    logger.warning("⚠️ Tenant '%s' NÃO encontrado para path %s", subdominio, request.path)
                    request.tenant = None
                    nr = 0
                    # Se o subdomínio não for liberado, bloquear acesso
                    if subdominio not in allowed:
                        raise Http404("Tenant não encontrado")
        else:
            # Sem subdomínio = site principal
            request.tenant = None
            nr = 0
            logger.info("ℹ️ Sem subdomínio (site principal)")


            

        # 3. Continua o fluxo
        resposta = self.get_response(request)
        # Proteção: alguns middlewares ou views podem (indevidamente) retornar None;
        # garantimos aqui que sempre retornamos um HttpResponse válido para evitar
        # erros posteriores em middlewares como o CommonMiddleware.
        if resposta is None:
            logger.warning("⚠️ get_response retornou None — substituindo por redirect('home_view')")
            try:
                home_path = reverse('home_view')
            except Exception:
                home_path = '/home_view/'

            if request.path != home_path:
                return redirect('home_view')

        logger.info(f"✅ Resposta gerada — Tenant ID: {nr}")

        if not subdominio:
            # Evita loop: se a requisição já for para a rota `home_view`, não redirecionar
            try:
                home_path = reverse('home_view')
            except Exception:
                home_path = '/home_view/'

            if request.path != home_path:
                logger.info("ℹ️ Sem subdomínio (site principal) — redirecionando para /home_view/")
                return redirect('home_view')

        return resposta
