from types import SimpleNamespace
from unittest.mock import patch

from django.http import Http404, HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from .views import relatorio_acessos


class RelatorioAcessosTests(SimpleTestCase):
    def request_for(self, host_tenant_id=None, user_tenant_id=7):
        request = RequestFactory().get('/painel/relatorios/acessos/')
        request.user = SimpleNamespace(is_authenticated=True, tenant_id=user_tenant_id)
        request.tenant = SimpleNamespace(id=host_tenant_id) if host_tenant_id else None
        return request

    def test_main_domain_and_own_subdomain_filter_by_user_tenant(self):
        for host_tenant_id in (None, 7):
            with self.subTest(host_tenant_id=host_tenant_id):
                with patch('analytics.views.AcessoSite.objects.filter') as query, patch(
                    'analytics.views.render', return_value=HttpResponse('ok')
                ):
                    response = relatorio_acessos(self.request_for(host_tenant_id))
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(query.call_args.kwargs['tenant_id'], 7)

    def test_other_tenant_and_user_without_tenant_are_rejected(self):
        for host_tenant_id, user_tenant_id in ((8, 7), (None, None)):
            with self.subTest(host_tenant_id=host_tenant_id, user_tenant_id=user_tenant_id):
                with self.assertRaises(Http404):
                    relatorio_acessos(self.request_for(host_tenant_id, user_tenant_id))

    def test_period_links_keep_report_path_despite_base_tag(self):
        from django.template.loader import render_to_string
        from django.urls import reverse
        html = render_to_string('painel/relatorio_acessos.html', {'period_days': 30})
        for days in (7, 30, 90):
            self.assertIn(f'href="{reverse("relatorio_acessos")}?dias={days}"', html)

    def test_period_parameter_controls_date_filter(self):
        from datetime import timedelta
        from django.utils import timezone
        for days in (7, 30, 90):
            with self.subTest(days=days):
                request = self.request_for()
                request.GET = {'dias': str(days)}
                with patch('analytics.views.AcessoSite.objects.filter') as query, patch(
                    'analytics.views.render', return_value=HttpResponse('ok')
                ) as render:
                    relatorio_acessos(request)
                self.assertEqual(query.call_args.kwargs['data_hora__date__gte'], timezone.localdate() - timedelta(days=days - 1))
                self.assertEqual(render.call_args.args[2]['period_days'], days)


class GoogleStatsTests(TestCase):
    def unlock(self):
        return self.client.post('/stats/', {'stats_pin': '1234'}, HTTP_HOST='localhost')

    def test_requests_four_digit_pin(self):
        response = self.client.get('/stats/', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Digite o PIN de quatro dígitos')
        denied = self.client.post('/stats/', {'stats_pin': '9999'}, HTTP_HOST='localhost')
        self.assertEqual(denied.status_code, 403)
        self.assertContains(denied, 'PIN incorreto', status_code=403)
        accepted = self.unlock()
        self.assertRedirects(accepted, '/stats/', fetch_redirect_response=False)

    def test_requires_global_property_id(self):
        self.unlock()
        response = self.client.get('/stats/', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VIAZAP_GOOGLE_ANALYTICS_PROPERTY_ID')

    @override_settings(VIAZAP_GOOGLE_ANALYTICS_PROPERTY_ID='123456789')
    @patch('analytics.views.get_google_analytics_report')
    def test_displays_global_viazap_report(self, report):
        from analytics.google_analytics import GoogleAnalyticsReport

        self.unlock()
        report.return_value = GoogleAnalyticsReport(
            totals={'activeUsers': 12, 'sessions': 18, 'screenPageViews': 30, 'eventCount': 50},
            daily=[], pages=[],
        )
        response = self.client.get('/stats/?dias=7', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Usuários ativos')
        report.assert_called_once_with(tenant_id='viazap', property_id='123456789', days=7)

    def test_anonymous_user_only_needs_pin(self):
        response = self.client.get('/stats/', HTTP_HOST='localhost')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Relatórios protegidos')

    def test_tenant_subdomain_cannot_access_global_stats(self):
        response = self.client.get('/stats/', HTTP_HOST='qualquer.localhost')
        self.assertEqual(response.status_code, 404)
