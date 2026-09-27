from django.urls import path

from . import views


urlpatterns = [
    path('', views.painel_whatsapp, name='painel_whatsapp'),
    path('conectar/', views.conectar, name='painel_whatsapp_conectar'),
    path('status/', views.status, name='painel_whatsapp_status'),
    path('desconectar/', views.desconectar, name='painel_whatsapp_desconectar'),
    path('mensagens/salvar/', views.salvar_mensagens, name='painel_whatsapp_salvar_mensagens'),
]
