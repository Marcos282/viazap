from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('tenants', '0016_tenantsettings_chamar_whatsapp'),
    ]

    operations = [
        migrations.CreateModel(
            name='AcessoSite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('data_hora', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('pagina', models.CharField(max_length=500)),
                ('visitor_key', models.CharField(max_length=64)),
                ('user_agent', models.TextField(blank=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='acessos_site', to='tenants.tenant')),
            ],
            options={
                'indexes': [
                    models.Index(fields=['tenant', 'data_hora'], name='analytics_a_tenant__2a1924_idx'),
                    models.Index(fields=['tenant', 'visitor_key', 'data_hora'], name='analytics_a_tenant__fac4fb_idx'),
                ],
            },
        ),
    ]
