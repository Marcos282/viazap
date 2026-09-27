from types import SimpleNamespace

from django.http import HttpResponse
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from .middleware import RootStoreRedirectMiddleware


class RootStoreRedirectMiddlewareTests(SimpleTestCase):
	def setUp(self):
		self.factory = RequestFactory()
		self.middleware = RootStoreRedirectMiddleware(lambda request: HttpResponse('home'))

	def test_authenticated_tenant_user_is_sent_to_store(self):
		request = self.factory.get('/', HTTP_HOST='x.localhost:8000')
		request.user = SimpleNamespace(is_authenticated=True, tenant_id=7)
		request.tenant = SimpleNamespace(id=7)

		response = self.middleware(request)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], '/loja/')

	def test_anonymous_user_with_valid_tenant_goes_to_store(self):
		request = self.factory.get('/', HTTP_HOST='x.localhost:8000')
		request.user = SimpleNamespace(is_authenticated=False, tenant_id=None)
		request.tenant = SimpleNamespace(id=7)

		response = self.middleware(request)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(response['Location'], '/loja/')

	def test_authenticated_user_from_another_tenant_receives_404(self):
		request = self.factory.get('/', HTTP_HOST='x.localhost:8000')
		request.user = SimpleNamespace(is_authenticated=True, tenant_id=8)
		request.tenant = SimpleNamespace(id=7)

		with self.assertRaises(Http404):
			self.middleware(request)

	def test_unknown_tenant_receives_404(self):
		request = self.factory.get('/', HTTP_HOST='x.localhost:8000')
		request.user = SimpleNamespace(is_authenticated=False, tenant_id=None)
		request.tenant = None

		with self.assertRaises(Http404):
			self.middleware(request)


class ProductionTenantRoutingTests(SimpleTestCase):
    def test_valid_production_subdomain_redirects_to_store(self):
        from unittest.mock import patch
        from .middleware import TenantMiddleware
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                request = RequestFactory().get('/', HTTP_HOST='andreia.viazap.net')
                request.user = SimpleNamespace(is_authenticated=authenticated, tenant_id=7)
                middleware = TenantMiddleware(lambda request: HttpResponse('home'))
                with patch('tenants.middleware.Tenant.objects.get', return_value=SimpleNamespace(id=7)):
                    response = middleware(request)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response['Location'], '/loja/')

    def test_unknown_production_subdomain_is_404(self):
        from unittest.mock import patch
        from .middleware import TenantMiddleware
        from .models import Tenant
        request = RequestFactory().get('/', HTTP_HOST='inexistente.viazap.net')
        middleware = TenantMiddleware(lambda request: HttpResponse('home'))
        with patch('tenants.middleware.Tenant.objects.get', side_effect=Tenant.DoesNotExist):
            with self.assertRaises(Http404):
                middleware(request)

    def test_main_domain_and_store_path_are_not_redirected(self):
        for host, path, tenant in (('viazap.net', '/', None), ('andreia.viazap.net', '/loja/', SimpleNamespace(id=7))):
            with self.subTest(host=host, path=path):
                request = RequestFactory().get(path, HTTP_HOST=host)
                request.tenant = tenant
                response = RootStoreRedirectMiddleware(lambda request: HttpResponse('ok'))(request)
                self.assertEqual(response.status_code, 200)

    def test_unknown_tenant_returns_http_404_on_public_and_panel_paths(self):
        from unittest.mock import patch
        from .models import Tenant
        with self.settings(
            DEBUG=False,
            ALLOWED_HOSTS=['.viazap.net'],
            MIDDLEWARE=['tenants.middleware.TenantMiddleware'],
            TEMPLATES=[{'BACKEND': 'django.template.backends.django.DjangoTemplates',
                        'OPTIONS': {'loaders': [('django.template.loaders.locmem.Loader',
                                                 {'404.html': 'Página não encontrada'})]}}],
        ):
            with patch('tenants.middleware.Tenant.objects.get', side_effect=Tenant.DoesNotExist):
                for path in ('/', '/loja/', '/painel/home/'):
                    with self.subTest(path=path):
                        response = self.client.get(path, HTTP_HOST='rafae.viazap.net')
                        self.assertEqual(response.status_code, 404)
