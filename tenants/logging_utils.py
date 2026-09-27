# Exemplo de configuração de logging mais avançada para o middleware
# Adicione no settings.py se quiser implementar logging em arquivo

import logging
import os
from datetime import datetime

# Configuração de logging para o middleware
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '[{asctime}] {levelname} | {name} | {message}',
            'style': '{',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'detailed',
        },
        'tenant_access_file': {
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'tenant_access.log'),
            'formatter': 'detailed',
        },
    },
    'loggers': {
        'tenants.middleware': {
            'handlers': ['console', 'tenant_access_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Função para log estruturado no middleware
def log_tenant_access(request, tenant):
    """
    Função para fazer log estruturado do acesso ao painel
    """
    logger = logging.getLogger('tenants.middleware')
    
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'tenant_name': tenant.name,
        'tenant_subdomain': tenant.subdomain,
        'ip_address': request.META.get('REMOTE_ADDR', 'N/A'),
        'url_path': request.path,
        'http_method': request.method,
        'user_agent': request.META.get('HTTP_USER_AGENT', 'N/A')[:200],
        'referer': request.META.get('HTTP_REFERER', 'Direct access'),
        'user': str(request.user) if hasattr(request, 'user') and request.user.is_authenticated else 'Anonymous',
        'session_key': request.session.session_key if hasattr(request, 'session') else 'N/A'
    }
    
    # Log estruturado para arquivo
    logger.info(f"PANEL_ACCESS: {log_data}")
    
    # Log formatado para console
    print("=" * 100)
    print(f"🏢 ACESSO AO PAINEL ADMINISTRATIVO - {log_data['timestamp']}")
    print("=" * 100)
    print(f"🏪 Tenant:           {log_data['tenant_name']} ({log_data['tenant_subdomain']})")
    print(f"📍 IP:               {log_data['ip_address']}")
    print(f"🔗 URL:              {log_data['url_path']}")
    print(f"📋 Método:           {log_data['http_method']}")
    print(f"👤 Usuário:          {log_data['user']}")
    print(f"🔄 Origem:           {log_data['referer']}")
    print(f"💻 User-Agent:       {log_data['user_agent']}")
    print(f"🔑 Sessão:           {log_data['session_key']}")
    print("=" * 100)