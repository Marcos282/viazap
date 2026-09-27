from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0003_user_data_expiracao_alter_user_email'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'ALTER TABLE customers_user '
                'ADD COLUMN IF NOT EXISTS email_confirmation_pending '
                'boolean NOT NULL DEFAULT false'
            ),
            reverse_sql=(
                'ALTER TABLE customers_user '
                'DROP COLUMN IF EXISTS email_confirmation_pending'
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='email_confirmation_pending',
                    field=models.BooleanField(default=False),
                ),
            ],
        ),
    ]