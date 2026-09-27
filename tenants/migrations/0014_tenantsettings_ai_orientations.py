from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tenants', '0013_tenant_aberto'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenantsettings',
            name='ai_orientations',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Instruções adicionais que a IA deve seguir no atendimento.',
                verbose_name='Orientações para a IA',
            ),
        ),
    ]