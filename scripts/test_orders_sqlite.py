"""Testes isolados sem exigir permissão CREATEDB no PostgreSQL local.

Cria o schema diretamente dos models; não substitui teste de migrations/locks no PostgreSQL.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'burger.settings')

from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}

import django
django.setup()
from django.apps import apps
settings.MIGRATION_MODULES = {app.label: None for app in apps.get_app_configs()}

from django.test.runner import DiscoverRunner
sys.exit(bool(DiscoverRunner(verbosity=1, interactive=False).run_tests(
    ['orders.tests', 'core.tests', 'customers.tests']
)))
