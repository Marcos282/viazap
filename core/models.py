from django.conf import settings
from django.db import models


class ChatSession(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='chat_sessions')
    session_key = models.CharField(max_length=255)
    introduction_complete = models.BooleanField(default=False)
    customer_phone = models.CharField(max_length=13, blank=True, default='')
    mode = models.CharField(max_length=10, choices=[('bot', 'Bot'), ('operator', 'Operador'), ('closed', 'Encerrada')], default='bot')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['tenant', 'session_key'], name='unique_chat_session_per_tenant')]


class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=[('customer', 'Cliente'), ('bot', 'Bot'), ('operator', 'Operador')])
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class AITokenUsage(models.Model):
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='ai_token_usage')
    model = models.CharField(max_length=255, blank=True)
    input_tokens = models.PositiveBigIntegerField(default=0)
    output_tokens = models.PositiveBigIntegerField(default=0)
    total_tokens = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Consumo de tokens da IA'
        verbose_name_plural = 'Consumo de tokens da IA'
