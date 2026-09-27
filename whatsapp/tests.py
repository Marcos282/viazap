from unittest.mock import patch

from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.test import RequestFactory, TestCase

from customers.models import Cliente, User
from orders.models import Ordem
from orders.services.status import change_payment, change_status
from tenants.models import Tenant, TenantSettings

from .models import MensagemProcesso, WhatsAppConfiguracao
from .services.evolution import EvolutionState
from .views import _tenant, conectar, desconectar, salvar_mensagens, status


class WhatsAppTenantTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(name='Loja Um', subdomain='loja-um')
        self.user = User.objects.create_user(
            email='loja1@example.com', username='loja-um', password='senha', tenant=self.tenant,
        )

    def request(self, method, path, *, user=None, tenant=None, host='loja-um.localhost'):
        request = getattr(self.factory, method.lower())(path, HTTP_HOST=host)
        request.user = self.user if user is None else user
        request.tenant = self.tenant if tenant is None else tenant
        return request

    def test_instance_name_is_deterministic_and_cannot_be_overridden(self):
        config = WhatsAppConfiguracao.objects.create(tenant=self.tenant, instance_name='injetado')
        self.assertEqual(config.instance_name, f'viazap_tenant_{self.tenant.pk}')
        config.instance_name = 'outro-nome'
        config.save()
        self.assertEqual(config.instance_name, f'viazap_tenant_{self.tenant.pk}')

    def test_rejects_another_tenant(self):
        other = Tenant.objects.create(name='Loja Dois', subdomain='loja-dois')
        with self.assertRaises(Http404):
            _tenant(self.request('get', '/', tenant=other, host='loja-dois.localhost'))

    def test_localhost_derives_tenant_from_authenticated_user(self):
        request = self.request('get', '/', tenant=None, host='localhost:8000')
        self.assertEqual(_tenant(request), self.tenant)
        self.assertEqual(request.tenant, self.tenant)

    def test_main_domain_derives_tenant_from_authenticated_user(self):
        request = self.request('get', '/', tenant=None, host='viazap.net')
        self.assertEqual(_tenant(request), self.tenant)
        self.assertEqual(request.tenant, self.tenant)

    def test_connect_requires_authentication(self):
        response = conectar(self.request('post', '/', user=AnonymousUser()))
        self.assertEqual(response.status_code, 403)

    @patch('whatsapp.views.django_messages.success')
    def test_saves_delivery_and_retail_messages_per_tenant(self, success):
        request = self.request('post', '/painel/whatsapp/mensagens/salvar/')
        request.POST = request.POST.copy()
        request.POST.update({
            'ativa_delivery_novo': 'on',
            'mensagem_delivery_novo': 'Olá, {cliente}! Pedido {pedido} recebido.',
            'mensagem_varejo_confirmado': 'Compra {pedido} confirmada.',
        })

        response = salvar_mensagens(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(MensagemProcesso.objects.filter(tenant=self.tenant).count(), 17)
        delivery = MensagemProcesso.objects.get(
            tenant=self.tenant, cenario='delivery', status_pedido='novo',
        )
        varejo = MensagemProcesso.objects.get(
            tenant=self.tenant, cenario='varejo', status_pedido='confirmado',
        )
        self.assertTrue(delivery.ativa)
        self.assertEqual(delivery.mensagem, 'Olá, {cliente}! Pedido {pedido} recebido.')
        self.assertFalse(varejo.ativa)
        self.assertEqual(varejo.mensagem, 'Compra {pedido} confirmada.')
        success.assert_called_once()

    @patch('whatsapp.views.EvolutionService')
    def test_connect_creates_qr_for_current_tenant(self, service_class):
        service = service_class.return_value
        service.create_instance.return_value = {'qrcode': {'base64': 'qr-base64'}}
        service.connection_state.return_value = EvolutionState('close')
        response = conectar(self.request('post', '/painel/whatsapp/conectar/'))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'aguardando_qr', 'qr_code': 'qr-base64'})
        service.create_instance.assert_called_once_with(self.tenant)
        config = WhatsAppConfiguracao.objects.get(tenant=self.tenant)
        self.assertEqual(config.status, WhatsAppConfiguracao.Status.AGUARDANDO_QR)

    @patch('whatsapp.views.EvolutionService')
    def test_status_persists_connected_number(self, service_class):
        service_class.return_value.connection_state.return_value = EvolutionState('open', '5511999999999')
        response = status(self.request('get', '/painel/whatsapp/status/'))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {'status': 'conectado', 'numero': '5511999999999'})
        config = WhatsAppConfiguracao.objects.get(tenant=self.tenant)
        self.assertEqual(config.status, WhatsAppConfiguracao.Status.CONECTADO)
        self.assertIsNotNone(config.conectado_em)

    @patch('whatsapp.views.EvolutionService')
    def test_disconnect_logs_out_only_current_tenant(self, service_class):
        config = WhatsAppConfiguracao.objects.create(
            tenant=self.tenant,
            status=WhatsAppConfiguracao.Status.CONECTADO,
            numero_whatsapp='5511999999999',
        )
        response = desconectar(self.request('post', '/painel/whatsapp/desconectar/'))
        self.assertEqual(response.status_code, 200)
        service_class.return_value.logout.assert_called_once_with(self.tenant)
        config.refresh_from_db()
        self.assertEqual(config.status, WhatsAppConfiguracao.Status.DESCONECTADO)
        self.assertEqual(config.numero_whatsapp, '')


class EvolutionPayloadIsolationTests(TestCase):
    @patch('whatsapp.services.evolution.EvolutionService._request')
    def test_find_instance_accepts_not_found_as_missing_instance(self, request):
        from whatsapp.services.evolution import EvolutionService

        tenant = Tenant.objects.create(name='Nova Loja', subdomain='nova-loja')
        request.return_value = None

        self.assertIsNone(EvolutionService().find_instance(tenant))
        self.assertTrue(request.call_args.kwargs['not_found_ok'])

    @patch('whatsapp.services.evolution.EvolutionService._request')
    def test_find_instance_ignores_wrong_instance_returned_by_api(self, request):
        from whatsapp.services.evolution import EvolutionService

        tenant = Tenant.objects.create(name='Loja', subdomain='loja')
        request.return_value = [
            {'instance': {'instanceName': 'viazap_tenant_999'}},
            {'instance': {'instanceName': f'viazap_tenant_{tenant.pk}'}},
        ]
        found = EvolutionService().find_instance(tenant)
        self.assertEqual(found['instance']['instanceName'], f'viazap_tenant_{tenant.pk}')


class AutomaticOrderMessageTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Loja Teste', subdomain='mensagens')
        self.settings = TenantSettings.load(self.tenant)
        self.settings.nome_loja = 'Mercado Teste'
        self.settings.save()
        self.user = User.objects.create_user(
            email='mensagens@example.com', username='mensagens', password='senha', tenant=self.tenant,
        )
        self.customer = Cliente.objects.create(
            tenant=self.tenant, nome='Maria', telefone='(11) 99999-8888', senha='x',
        )

    @patch('whatsapp.services.notifications.EvolutionService')
    def test_status_change_sends_configured_message_after_commit(self, service_class):
        service = service_class.return_value
        service.connection_state.return_value = EvolutionState('open')
        service._request.return_value = {'key': {'id': 'message-id'}, 'status': 'PENDING'}
        MensagemProcesso.objects.create(
            tenant=self.tenant,
            cenario='varejo',
            status_pedido='confirmado',
            ativa=True,
            mensagem='Olá, {cliente}! Pedido {pedido} confirmado na {loja}. Total: {total}.',
        )
        order = Ordem.objects.create(
            tenant=self.tenant,
            cliente=self.customer,
            tipo_operacao='varejo',
            tipo_entrega='entrega',
            valor_total=Decimal('25.50'),
            tx_entrega=Decimal('4.50'),
        )

        with self.captureOnCommitCallbacks(execute=True):
            change_status(
                ordem_id=order.pk,
                tenant_id=self.tenant.pk,
                novo_status='confirmado',
                expected_status='novo',
                usuario=self.user,
            )

        service._request.assert_called_once_with(
            'POST',
            f'/message/sendText/viazap_tenant_{self.tenant.pk}',
            json={
                'number': '5511999998888',
                'text': f'Olá, Maria! Pedido {order.pk} confirmado na Mercado Teste. Total: R$ 30,00.',
            },
        )

    @patch('whatsapp.services.notifications.EvolutionService')
    def test_inactive_process_does_not_contact_evolution(self, service_class):
        MensagemProcesso.objects.create(
            tenant=self.tenant,
            cenario='delivery',
            status_pedido='processando',
            ativa=False,
            mensagem='Pedido aceito.',
        )
        order = Ordem.objects.create(
            tenant=self.tenant,
            cliente=self.customer,
            tipo_operacao='delivery',
            tipo_entrega='entrega',
        )

        with self.captureOnCommitCallbacks(execute=True):
            change_status(
                ordem_id=order.pk,
                tenant_id=self.tenant.pk,
                novo_status='processando',
                expected_status='novo',
                usuario=self.user,
            )

        service_class.assert_not_called()

    @patch('whatsapp.services.notifications.EvolutionService')
    def test_payment_change_sends_configured_message_once(self, service_class):
        service = service_class.return_value
        service.connection_state.return_value = EvolutionState('open')
        service._request.return_value = {'key': {'id': 'payment-message-id'}, 'status': 'PENDING'}
        MensagemProcesso.objects.create(
            tenant=self.tenant,
            cenario='pagamento',
            status_pedido='pago',
            ativa=True,
            mensagem='Pagamento {status_pagamento} do pedido {pedido}: {total} via {forma_pagamento}.',
        )
        order = Ordem.objects.create(
            tenant=self.tenant,
            cliente=self.customer,
            tipo_operacao='varejo',
            valor_total=Decimal('45.00'),
            formade_pagamento='Pix',
        )

        with self.captureOnCommitCallbacks(execute=True):
            change_payment(
                ordem_id=order.pk,
                tenant_id=self.tenant.pk,
                status_pagamento='pago',
                usuario=self.user,
            )
        with self.captureOnCommitCallbacks(execute=True):
            change_payment(
                ordem_id=order.pk,
                tenant_id=self.tenant.pk,
                status_pagamento='pago',
                usuario=self.user,
            )

        service._request.assert_called_once_with(
            'POST',
            f'/message/sendText/viazap_tenant_{self.tenant.pk}',
            json={
                'number': '5511999998888',
                'text': f'Pagamento Pago do pedido {order.pk}: R$ 45,00 via Pix.',
            },
        )
