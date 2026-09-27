# tenants/middleware.py

from django.http import Http404, HttpResponseForbidden
from django.urls import resolve
from tenants.models import Tenant

class SubdomainMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Pega o host e remove a porta, se presente
        host = request.get_host().split(':')[0]  # Ex: 'andre.localhost:8000' -> 'andre.localhost'
        parts = host.split('.')

        # Para localhost, aceita subdomínio com len(parts) >= 2
        subdomain = parts[0] if len(parts) >= 2 and parts[-1] == 'localhost' else None

        # Proteção: bloquear acesso ao painel com subdomínio
        if subdomain and request.path.startswith('/painel/'):
            # Constrói URL sem subdomínio para redirecionamento
            protocol = 'https' if request.is_secure() else 'http'
            base_domain = '.'.join(parts[1:])  # Remove o subdomínio
            port = f":{request.get_port()}" if request.get_port() not in ['80', '443'] else ''
            painel_url = f"{protocol}://{base_domain}{port}/painel/home/"
            
            return HttpResponseForbidden(
                f"Acesso negado: URLs do painel não podem ser acessadas via subdomínio. "
                f"Acesse diretamente pelo domínio principal.<br> "
                f"<a href='{painel_url}'>Ir para o painel</a>"
            )
        
        # Busca tenant no banco
        tenant = Tenant.objects.filter(subdomain=subdomain).first()
        # Se não encontrar tenant e não for acesso ao painel, lança 404
        if not tenant:
            if not request.path.startswith('/painel/'): 
                raise Http404("Tenant não encontrado")
        else:
            request.tenant = tenant  # Adiciona tenant ao request

        # Faz log do acesso ao painel
        if request.path.startswith('/painel/'):
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            ip_address = request.META.get('REMOTE_ADDR', 'N/A')
            user_info = f"{request.user.username}" if hasattr(request, 'user') and request.user.is_authenticated else "Anônimo"
            
            # Informações do tenant (se existir)
            tenant_info = "Painel Principal (sem tenant)"
            if hasattr(request, 'tenant') and request.tenant:
                tenant_info = f"{request.tenant.name} ({request.tenant.subdomain})"
            
            # Log formatado e elegante
            print("\n" + "🟦" * 50)
            print(f"🏢 PAINEL ADMINISTRATIVO | {timestamp}")
            print("🟦" * 50)
            print(f"🏪 Contexto: {tenant_info}")
            print(f"📍 IP: {ip_address} | 👤 Usuário: {user_info}")
            print(f"🔗 Rota: {request.method} {request.path}")
            print("🟦" * 50 + "\n")
                
        return self.get_response(request)