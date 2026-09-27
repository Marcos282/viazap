from decimal import Decimal
from importlib import import_module
from types import SimpleNamespace
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, RequestFactory, Client
from django.utils import timezone
from django.urls import reverse
from customers.models import User, Cliente, EnderecoEntrega
from tenants.models import Tenant, TenantSettings
from orders.models import Ordem, OrdemItem, HistoricoStatusPedido
from orders.services.status import (change_status, get_next_action, get_status_label,
    change_delivery, change_payment, get_whatsapp_message, get_whatsapp_url)
from orders.services.dashboard import get_indicators
from orders import panel_views
from customers.views_auth import painel_view, painel_pedidos_dados, painel_pedidos_pendentes_count
from menu.models import Produto, Category


class OrderFlowTests(TestCase):
    def setUp(self):
        self.a = Tenant.objects.create(name='Loja A', subdomain='flow-a')
        self.b = Tenant.objects.create(name='Loja B', subdomain='flow-b')
        self.user = User.objects.create_user(email='flow-a@example.com', password='test', username='flow-a', tenant=self.a)
        self.config = TenantSettings.load(self.a)
        self.factory = RequestFactory()

    def order(self, scenario='varejo', delivery='entrega', **kwargs):
        return Ordem.objects.create(tenant=self.a, tipo_operacao=scenario, tipo_entrega=delivery, **kwargs)

    def advance(self, order, status):
        return change_status(ordem_id=order.pk, tenant_id=self.a.pk, usuario=self.user,
                             novo_status=status, expected_status=order.status)

    def request(self, method='post', data=None, host_tenant=None):
        req = getattr(self.factory, method)('/', data or {})
        req.user = self.user
        req.tenant = host_tenant or self.a
        return req

    def test_new_order_snapshots_tenant_scenario(self):
        self.config.tipo_operacao = 'delivery'
        self.config.save()
        order = Ordem.objects.create(tenant=self.a)
        self.assertEqual(order.tipo_operacao, 'delivery')
        self.assertEqual(order.status, 'novo')
        self.assertEqual(order.status_pagamento, 'pendente')
        self.config.tipo_operacao = 'varejo'
        self.config.save()
        order.refresh_from_db()
        self.assertEqual(order.tipo_operacao, 'delivery')
        self.assertEqual(Ordem.objects.create(tenant=self.a).tipo_operacao, 'varejo')

    def test_all_four_flows(self):
        for scenario in ['delivery', 'varejo']:
            for delivery in ['entrega', 'retirada']:
                with self.subTest(scenario=scenario, delivery=delivery):
                    order = self.order(scenario, delivery)
                    flow = (['processando'] if scenario == 'delivery' else ['confirmado', 'processando'])
                    flow += ['pronto'] + (['enviado'] if delivery == 'entrega' else []) + ['concluido']
                    for status in flow:
                        self.assertEqual(get_next_action(order)['status'], status)
                        order = self.advance(order, status)
                    self.assertTrue(order.completo)
                    self.assertIsNotNone(order.concluido_em)
                    self.assertIsNone(get_next_action(order))
                    self.assertEqual(order.historico_status.count(), len(flow))
                    self.assertEqual(order.status_pagamento, 'pendente')

    def test_invalid_jump_and_stale_request(self):
        order = self.order()
        with self.assertRaises(ValidationError):
            self.advance(order, 'enviado')
        order = self.advance(order, 'confirmado')
        with self.assertRaises(ValidationError):
            change_status(ordem_id=order.pk, tenant_id=self.a.pk, usuario=self.user,
                          novo_status='processando', expected_status='novo')
        self.assertEqual(order.historico_status.count(), 1)

    def test_repeated_action_has_no_duplicate_history(self):
        order = self.advance(self.order(), 'confirmado')
        self.advance(order, 'confirmado')
        self.assertEqual(order.historico_status.count(), 1)

    def test_cancel_keeps_order_and_payment(self):
        order = self.order(status_pagamento='pago')
        order = self.advance(order, 'cancelado')
        self.assertTrue(Ordem.objects.filter(pk=order.pk).exists())
        self.assertEqual(order.status_pagamento, 'pago')
        self.assertIsNone(get_next_action(order))
        with self.assertRaises(ValidationError):
            self.advance(order, 'confirmado')

    def test_completed_order_cannot_cancel(self):
        order = self.order(status='concluido', completo=True)
        with self.assertRaises(ValidationError):
            self.advance(order, 'cancelado')

    def test_unknown_delivery_must_be_resolved(self):
        order = self.order(delivery='a_combinar', status='processando')
        self.assertIsNone(get_next_action(order))
        with self.assertRaises(ValidationError):
            self.advance(order, 'pronto')
        order = change_delivery(ordem_id=order.pk, tenant_id=self.a.pk, usuario=self.user, tipo_entrega='retirada')
        order = self.advance(order, 'pronto')
        self.assertEqual(get_next_action(order)['status'], 'concluido')
        with self.assertRaises(ValidationError):
            change_delivery(ordem_id=order.pk, tenant_id=self.a.pk, usuario=self.user, tipo_entrega='entrega')

    def test_payment_changes_do_not_change_order_status(self):
        order = self.order()
        order = change_payment(ordem_id=order.pk, tenant_id=self.a.pk, usuario=self.user, status_pagamento='pago')
        self.assertEqual(order.status, 'novo')
        self.assertFalse(order.completo)
        self.assertEqual(order.historico_status.count(), 0)
        order = change_payment(ordem_id=order.pk, tenant_id=self.a.pk, usuario=self.user, status_pagamento='estornado')
        self.assertEqual(order.status_pagamento, 'estornado')

    def test_foreign_order_rejected_by_every_endpoint(self):
        foreign = Ordem.objects.create(tenant=self.b)
        for view, data in [(panel_views.status, {'status': 'confirmado', 'status_atual': 'novo'}),
                           (panel_views.cancel, {'status_atual': 'novo'}),
                           (panel_views.delivery, {'tipo_entrega': 'entrega'}),
                           (panel_views.payment, {'status_pagamento': 'pago'})]:
            self.assertEqual(view(self.request(data=data), foreign.pk).status_code, 404)
        self.assertEqual(panel_views.history(self.request('get'), foreign.pk).status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, 'novo')

    def test_mismatched_host_rejected(self):
        for view in [painel_view, painel_pedidos_dados, painel_pedidos_pendentes_count]:
            self.assertEqual(view(self.request('get', host_tenant=self.b)).status_code, 403)
        self.assertEqual(panel_views.history(self.request('get', host_tenant=self.b), self.order().pk).status_code, 403)

    def test_panel_and_ajax_do_not_include_foreign_customer(self):
        customer = Cliente.objects.create(tenant=self.b, nome='CLIENTE PRIVADO', senha='x')
        Ordem.objects.create(tenant=self.b, cliente=customer)
        self.order()
        for view in [painel_view, painel_pedidos_dados]:
            response = view(self.request('get'))
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('CLIENTE PRIVADO', response.content.decode())

    def test_status_requires_post_and_csrf(self):
        order = self.order()
        self.assertEqual(panel_views.status(self.request('get'), order.pk).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(reverse('pedido_status', args=[order.pk]),
                               {'status': 'confirmado', 'status_atual': 'novo'}, HTTP_HOST='flow-a.localhost')
        self.assertEqual(response.status_code, 403)

    def test_indicators_are_scoped_and_use_completion_date(self):
        self.order()
        self.order(status='concluido', completo=True, concluido_em=timezone.now(),
                   valor_total=Decimal('50'), tx_entrega=Decimal('5'))
        self.order(status='concluido', completo=True, valor_total=Decimal('500'))
        Ordem.objects.create(tenant=self.b, status='concluido', concluido_em=timezone.now(), valor_total=999)
        data = get_indicators(self.a)
        self.assertEqual(data['novos'], 1)
        self.assertEqual(data['concluidos'], 1)
        self.assertEqual(data['faturamento'], Decimal('55'))

    def test_labels_and_whatsapp_respect_scenario(self):
        order = self.order(status='processando')
        self.assertEqual(get_status_label(order), 'Separando pedido')
        self.assertIn('separando os produtos', get_whatsapp_message(order))
        order.tipo_operacao = 'delivery'
        self.assertEqual(get_status_label(order), 'Em preparação')
        self.assertIn('preparado', get_whatsapp_message(order))
        order.status = 'pronto'
        order.tipo_entrega = 'retirada'
        self.assertIn('retirada', get_whatsapp_message(order))

    def test_no_whatsapp_link_without_customer_phone(self):
        self.assertEqual(get_whatsapp_url(self.order()), '')

    def test_historical_price_survives_catalog_change(self):
        category = Category.objects.create(tenant=self.a, name='Categoria')
        product = Produto.objects.create(tenant=self.a, category=category, nome='Item', price=99)
        item = OrdemItem.objects.create(tenant=self.a, ordem=self.order(), produto=product,
                                       preco_unitario=Decimal('15'), quantidade=2)
        self.assertEqual(item.get_total, Decimal('30'))
        item.produto = None
        self.assertEqual(item.get_total, Decimal('30'))

    def test_backfill_preserves_legacy_orders(self):
        order = self.order(scenario='delivery', completo=True)
        unknown = self.order(scenario='delivery')
        pickup = self.order(formade_pagamento='Retirada no local')
        EnderecoEntrega.objects.create(tenant=self.a, ordem=order, endereco='Rua', cidade='Cidade')
        migrate = import_module('orders.migrations.0005_backfill_order_flow').populate
        before = Ordem.objects.count()
        migrate(apps, SimpleNamespace(connection=connection))
        order.refresh_from_db()
        unknown.refresh_from_db()
        pickup.refresh_from_db()
        self.assertEqual(Ordem.objects.count(), before)
        self.assertEqual(order.tipo_operacao, 'varejo')
        self.assertEqual(order.status, 'concluido')
        self.assertIsNone(order.concluido_em)
        self.assertEqual(order.tipo_entrega, 'entrega')
        self.assertEqual(unknown.tipo_entrega, 'a_combinar')
        self.assertEqual(pickup.tipo_entrega, 'retirada')
        self.assertEqual(HistoricoStatusPedido.objects.count(), 0)

    def test_checkout_ignores_posted_tenant_and_snapshots_price(self):
        from core.views import checkout
        category = Category.objects.create(tenant=self.a, name='Categoria')
        product = Produto.objects.create(tenant=self.a, category=category, nome='Item', price=Decimal('12'))
        request = self.request(data={'tenant_id': self.b.pk})
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()
        request.session['cart'] = {str(product.pk): 2}
        response = checkout(request)
        self.assertEqual(response.status_code, 200)
        order = Ordem.objects.get()
        self.assertEqual(order.tenant_id, self.a.pk)
        self.assertEqual(order.valor_total, Decimal('24'))
        self.assertEqual(order.ordemitem_set.get().preco_unitario, Decimal('12'))

    def test_checkout_foreign_product_rolls_back(self):
        from core.views import checkout
        from django.http import Http404
        category = Category.objects.create(tenant=self.b, name='Categoria')
        product = Produto.objects.create(tenant=self.b, category=category, nome='Item', price=12)
        request = self.request()
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()
        request.session['cart'] = {str(product.pk): 2}
        with self.assertRaises(Http404):
            checkout(request)
        self.assertEqual(Ordem.objects.count(), 0)

    def test_config_saves_scenario_and_rejects_invalid_value(self):
        from customers.views_auth import painel_configuracao
        response = painel_configuracao(self.request(data={'tipo_operacao': 'delivery'}))
        self.assertEqual(response.status_code, 200)
        self.config.refresh_from_db()
        self.assertEqual(self.config.tipo_operacao, 'delivery')
        response = painel_configuracao(self.request(data={'tipo_operacao': 'invalido'}))
        self.assertEqual(response.status_code, 400)
        self.config.refresh_from_db()
        self.assertEqual(self.config.tipo_operacao, 'delivery')

    def test_checkout_receipt_rejects_another_tenants_order(self):
        from core.views import checkout_sucesso
        foreign = Ordem.objects.create(tenant=self.b)
        request = self.request('get')
        request.session = {'last_pedido_info': {'pedido_id': foreign.pk, 'nome': 'SEGREDO'}}
        response = checkout_sucesso(request)
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('SEGREDO', response.content.decode())

    def test_history_records_actor_and_statuses(self):
        order = self.advance(self.order(), 'confirmado')
        entry = order.historico_status.get()
        self.assertEqual(entry.usuario_id, self.user.pk)
        self.assertEqual(entry.status_anterior, 'novo')
        self.assertEqual(entry.status_novo, 'confirmado')
        self.assertEqual(panel_views.history(self.request('get'), order.pk).status_code, 200)

    def test_status_endpoint_updates_existing_order(self):
        order = self.order()
        response = panel_views.status(self.request(data={'status': 'confirmado', 'status_atual': 'novo'}), order.pk)
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, 'confirmado')

    def test_legacy_completed_unknown_delivery_does_not_claim_delivered(self):
        order = self.order(delivery='a_combinar', status='concluido')
        message = get_whatsapp_message(order)
        self.assertIn('concluído', message)
        self.assertNotIn('entregue', message)
        self.assertNotIn('retirado', message)

    def test_customer_modal_creates_missing_customer_and_saves_notes(self):
        order = self.order()
        response = panel_views.customer(self.request(data={
            'nome': 'Maria', 'whatsapp': '(11) 99999-8888', 'observacoes': 'Entregar à tarde',
        }), order.pk)
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.cliente.tenant_id, self.a.pk)
        self.assertEqual(order.cliente.nome, 'Maria')
        self.assertEqual(order.cliente.telefone, '5511999998888')
        self.assertEqual(order.observacoes, 'Entregar à tarde')
        self.assertEqual(order.status, 'novo')
        self.assertIn('5511999998888', get_whatsapp_url(order))

    def test_customer_update_reuses_linked_customer(self):
        customer = Cliente.objects.create(tenant=self.a, nome='Antigo', telefone='11999998888', senha='x')
        order = self.order(cliente=customer)
        response = panel_views.customer(self.request(data={
            'nome': 'Novo nome', 'whatsapp': '11999998888', 'observacoes': 'Observação',
        }), order.pk)
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.cliente_id, customer.pk)
        self.assertEqual(Cliente.objects.filter(tenant=self.a).count(), 1)
        self.assertEqual(order.cliente.nome, 'Novo nome')

    def test_customer_update_rejects_foreign_order(self):
        order = Ordem.objects.create(tenant=self.b)
        response = panel_views.customer(self.request(data={
            'nome': 'Maria', 'whatsapp': '11999998888',
        }), order.pk)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Cliente.objects.exists())

    def test_customer_update_invalid_phone_does_not_create_customer(self):
        order = self.order()
        response = panel_views.customer(self.request(data={'nome': 'Maria', 'whatsapp': '123'}), order.pk)
        self.assertEqual(response.status_code, 409)
        order.refresh_from_db()
        self.assertIsNone(order.cliente_id)
        self.assertFalse(Cliente.objects.exists())

    def test_checkout_session_serializes_delivery_and_whatsapp_receipts(self):
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.contrib.sessions.backends.db import SessionStore
        from orders.views import pedido_delivery, pedido_whatsapp
        from core.views import checkout_sucesso
        category = Category.objects.create(tenant=self.a, name='Categoria')
        product = Produto.objects.create(tenant=self.a, category=category, nome='Produto', price=Decimal('19.90'))
        self.config.delivery = True
        self.config.taxa_entrega = Decimal('4.50')
        self.config.whatsapp = '5511999998888'
        self.config.save()
        for view, expected_total in [(pedido_delivery, 44.30), (pedido_whatsapp, 39.80)]:
            with self.subTest(view=view.__name__):
                request = self.request(data={
                    'nome': 'Cliente', 'whatsapp': '11999998888',
                    'endereco_rua': 'Rua de teste', 'cidade': 'São Paulo', 'estado': 'SP',
                    'endereco_cep': '01001000', 'endereco_bairro': 'Sé', 'endereco_numero': '10',
                    'endereco_referencia': '', 'endereco_complemento': '',
                    'forma_pagamento': '1',
                })
                middleware = SessionMiddleware(lambda req: None)
                middleware.process_request(request)
                request.session['cart'] = {str(product.pk): 2}
                response = middleware.process_response(request, view(request))
                self.assertEqual(response.status_code, 302)
                # Recarrega pelo serializador real da sessão, não apenas pelo dict da view.
                restored = SessionStore(session_key=request.session.session_key)
                receipt = restored['last_pedido_info']
                self.assertEqual(receipt['subtotal'], 39.80)
                self.assertEqual(receipt['total'], expected_total)
                self.assertEqual(receipt['produtos'][0]['preco'], 19.90)
                self.assertEqual(receipt['produtos'][0]['valor'], 39.80)
                self.assertEqual(restored['cart'], {})
                order = Ordem.objects.get(pk=receipt['pedido_id'])
                self.assertEqual(order.valor_total, Decimal('39.80'))
                self.assertEqual(order.ordemitem_set.get().preco_unitario, Decimal('19.90'))
                request.session = restored
                self.assertEqual(checkout_sucesso(request).status_code, 200)
