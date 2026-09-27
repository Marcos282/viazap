from django.db import models
from tenants.models import Tenant


class AcessoSite(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='acessos_site')
    data_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    pagina = models.CharField(max_length=500)
    visitor_key = models.CharField(max_length=64)
    user_agent = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'data_hora']),
            models.Index(fields=['tenant', 'visitor_key', 'data_hora']),
        ]
