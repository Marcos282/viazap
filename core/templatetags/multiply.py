from django import template
import os

register = template.Library()

@register.filter
def multiply(value, arg):
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def basename(value):
    """Retorna apenas o nome do arquivo (sem o caminho)"""
    if value:
        return os.path.basename(str(value))
    return ''

@register.simple_tag(takes_context=True)
def status_loja(context):
    """
    Template tag para verificar o status da loja (aberta/fechada)
    
    Uso no template:
    {% status_loja as loja_status %}
    {{ loja_status.status_texto }}
    
    Ou diretamente:
    {% status_loja %}
    """
    from core.utils import verificar_loja_aberta
    
    request = context.get('request')
    if not request:
        return {
            'aberta': False,
            'status_texto': 'Erro: contexto de requisição não encontrado',
            'proximo_evento': None,
            'horarios_hoje': None
        }
    
    return verificar_loja_aberta(request)

@register.filter
def esta_aberta(user):
    """
    Filtro simples para verificar se a loja do usuário está aberta
    
    Uso no template:
    {% if user|esta_aberta %}
        Loja aberta!
    {% endif %}
    """
    if not user or not hasattr(user, 'tenant') or not user.tenant:
        return False
    
    return user.tenant.esta_aberto_agora()
