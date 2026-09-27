from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('tenants', '0014_tenantsettings_ai_orientations'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tenantsettings',
            name='ai_orientations',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Instruções adicionais que a IA deve seguir no atendimento.',
                null=True,
                verbose_name='Orientações para a IA',
            ),
        ),
    ]