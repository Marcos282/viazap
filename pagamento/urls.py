from django.urls import path
from . import views

urlpatterns = [
    path('', views.pagamento, name='pagamento'),
    path('sucesso/', views.pagamento_sucesso, name='pagamento_sucesso'),
    path('falha/', views.pagamento_falha, name='pagamento_falha'),
    path('pendente/', views.pagamento_pendente, name='pagamento_pendente'),
    path('webhook/mercadopago/', views.webhook_mercadopago, name='webhook_mercadopago'),
    path('webhook/log/', views.webhook_log, name='webhook_log'),
    path('comprovante/', views.consultar_comprovante, name='consultar_comprovante'),
]