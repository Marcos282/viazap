PROCESSOS = {
    'delivery': [
        ('novo', 'Pedido recebido', 'clipboard-list', 'Olá, {cliente}! Recebemos o pedido #{pedido} na {loja}. Em breve ele será aceito.'),
        ('processando', 'Pedido aceito / em preparação', 'utensils', 'Pedido aceito, {cliente}! 👨‍🍳 Já estamos preparando o pedido #{pedido}.'),
        ('pronto', 'Pedido pronto', 'check-circle', 'Boa notícia, {cliente}! O pedido #{pedido} está pronto. Modalidade: {entrega}.'),
        ('enviado', 'Saiu para entrega', 'motorcycle', 'Seu pedido #{pedido} saiu para entrega! 🛵 Fique de olho, {cliente}.'),
        ('concluido', 'Pedido concluído', 'flag-checkered', 'Pedido #{pedido} concluído. Obrigado por escolher a {loja}, {cliente}! 💚'),
        ('cancelado', 'Pedido cancelado', 'times-circle', 'Olá, {cliente}. O pedido #{pedido} foi cancelado. Fale conosco se precisar de ajuda.'),
    ],
    'varejo': [
        ('novo', 'Pedido recebido', 'clipboard-list', 'Olá, {cliente}! Recebemos o pedido #{pedido} na {loja}. Em breve confirmaremos os itens.'),
        ('confirmado', 'Pedido confirmado', 'thumbs-up', 'Tudo certo, {cliente}! O pedido #{pedido} foi confirmado. Total: {total}.'),
        ('processando', 'Separando produtos', 'boxes', 'Estamos separando os produtos do pedido #{pedido}, {cliente}.'),
        ('pronto', 'Pronto para envio ou retirada', 'box-open', 'O pedido #{pedido} está pronto para {entrega}. 📦'),
        ('enviado', 'Pedido enviado', 'shipping-fast', 'Seu pedido #{pedido} foi enviado! Avisaremos quando a entrega for concluída.'),
        ('concluido', 'Entregue ou retirado', 'check-double', 'Pedido #{pedido} concluído com sucesso. Obrigado pela compra, {cliente}!'),
        ('cancelado', 'Pedido cancelado', 'times-circle', 'Olá, {cliente}. O pedido #{pedido} foi cancelado. Fale conosco se precisar de ajuda.'),
    ],
    'pagamento': [
        ('pendente', 'Pagamento pendente', 'clock', 'Olá, {cliente}. O pagamento do pedido #{pedido} está pendente. Forma de pagamento: {forma_pagamento}.'),
        ('pago', 'Pagamento confirmado', 'check-circle', 'Pagamento do pedido #{pedido} confirmado! Valor: {total}. Obrigado, {cliente}!'),
        ('cancelado', 'Pagamento cancelado', 'times-circle', 'Olá, {cliente}. O pagamento do pedido #{pedido} foi cancelado. Entre em contato com a {loja} se precisar de ajuda.'),
        ('estornado', 'Pagamento estornado', 'undo', 'O pagamento do pedido #{pedido} foi estornado. Consulte sua instituição financeira para acompanhar o crédito.'),
    ],
}

VARIAVEIS = (
    'cliente', 'pedido', 'telefone', 'total', 'loja', 'status', 'entrega',
    'forma_pagamento', 'status_pagamento',
)


def mensagens_do_tenant(tenant):
    from .models import MensagemProcesso

    salvas = {
        (item.cenario, item.status_pedido): item
        for item in MensagemProcesso.objects.filter(tenant=tenant)
    }
    grupos = []
    for cenario, processos in PROCESSOS.items():
        itens = []
        for status, titulo, icone, padrao in processos:
            salva = salvas.get((cenario, status))
            itens.append({
                'status': status,
                'titulo': titulo,
                'icone': icone,
                'mensagem': salva.mensagem if salva else padrao,
                'ativa': salva.ativa if salva else True,
            })
        grupos.append({'cenario': cenario, 'itens': itens})
    return grupos
