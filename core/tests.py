from datetime import datetime, timedelta

from django.test import SimpleTestCase, TestCase, RequestFactory
from django.utils import timezone

from .ai_chat import (
    add_chat_message,
    chat_session_belongs_to_tenant,
    fallback_reply,
    ensure_chat_session_state,
    get_chat_messages,
    list_active_chat_sessions,
    reset_idle_operator_session,
    set_chat_session_mode,
)
from .utils import calcular_dias_restantes, gravar_os_dias, normalizar_datetime


class ExpiracaoTests(SimpleTestCase):
    def test_calcula_dias_restantes_com_data_sem_timezone(self):
        agora = datetime(2026, 8, 23, 18, 0)
        data_expiracao = agora + timedelta(days=5)

        self.assertEqual(calcular_dias_restantes(data_expiracao, agora), 5)

    def test_preserva_data_com_timezone(self):
        valor = timezone.now()

        self.assertIs(normalizar_datetime(valor), valor)

    def test_gravar_os_dias_soma_saldo_restante_e_credito(self):
        agora = timezone.now()

        nova_data = gravar_os_dias(5, agora, 30)

        self.assertEqual(nova_data, agora + timedelta(days=35))
        self.assertTrue(timezone.is_aware(nova_data))

    def test_gravar_os_dias_inicia_credito_quando_nao_ha_saldo(self):
        agora = timezone.now()

        nova_data = gravar_os_dias(-1, agora, 30)

        self.assertEqual(nova_data, agora + timedelta(days=30))


class AIBotFallbackTests(SimpleTestCase):
    def setUp(self):
        self.context = {
            'store': {
                'nome': 'Burger House',
                'descricao': 'Hamburgueres artesanais',
                'segmento': 'delivery',
                'whatsapp': '(47) 99999-0000',
                'endereco': 'Rua das Flores, 123, Centro, Itajaí, SC',
                'taxa_entrega': 'R$ 8,00',
                'pedido_minimo': 'R$ 25,00',
                'formas_pagamento': ['PIX', 'cartao de credito', 'dinheiro'],
                'aberto': True,
            },
            'cliente': {'nome': 'Maria', 'telefone': '47999990000', 'cidade': 'Itajaí', 'pedidos_pendentes': 0},
            'categorias': ['Lanches', 'Bebidas'],
            'produtos': [
                {'nome': 'X-Burger', 'categoria': 'Lanches', 'descricao': 'Hamburguer com queijo', 'preco': 'R$ 29,90'},
                {'nome': 'Refrigerante', 'categoria': 'Bebidas', 'descricao': 'Lata 350ml', 'preco': 'R$ 8,00'},
            ],
        }

    def test_responde_endereco_e_pagamento_sem_ia(self):
        endereco = fallback_reply('Qual é o endereço?', self.context)
        pagamento = fallback_reply('Quais são as formas de pagamento?', self.context)
        ent = fallback_reply('Qual a taxa de entrega?', self.context)
        whatsapp = fallback_reply('Qual é o WhatsApp?', self.context)

        self.assertIn('Rua das Flores', endereco)
        self.assertIn('PIX', pagamento)
        self.assertIn('R$ 8,00', ent)
        self.assertIn('(47) 99999-0000', whatsapp)

    def test_responde_pelo_nome_do_produto_no_fallback(self):
        resposta = fallback_reply('Quero o X-Burger', self.context)

        self.assertIn('X-Burger', resposta)
        self.assertIn('R$ 29,90', resposta)


class WhatsAppHandoffTests(SimpleTestCase):
    def test_missing_address_refers_to_store_contact(self):
        reply = fallback_reply('Qual o endereço?', {'store': {'nome': 'Seu nome completo', 'endereco': ' ', 'whatsapp': '47999991234'}})
        self.assertIn('endereço da loja ainda não está cadastrado', reply)
        self.assertIn('47999991234', reply)
        self.assertNotIn('Seu nome completo', reply)

    def test_missing_address_and_phone(self):
        reply = fallback_reply('Onde fica?', {'store': {}})
        self.assertIn('confirme com um atendente', reply)
        self.assertNotIn('WhatsApp:', reply)

    def test_unknown_question_uses_store_whatsapp(self):
        from .ai_chat import fallback_reply
        reply = fallback_reply('Uma dúvida sem informação disponível', {'store': {'whatsapp': '47999991234'}})
        self.assertIn('47999991234', reply)
        self.assertIn('atendente', reply)

    def test_missing_whatsapp_is_not_invented(self):
        from .ai_chat import whatsapp_handoff_reply
        self.assertIn('não está cadastrado', whatsapp_handoff_reply({'store': {}}))

    def test_empty_ai_response_returns_whatsapp(self):
        from unittest.mock import patch, Mock
        from django.test import override_settings
        from .ai_chat import ask_ai_assistant
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': ' '}}]}
        with override_settings(AI_CHAT_API_KEY='test'), patch('core.ai_chat.requests.post', return_value=response):
            reply, enabled = ask_ai_assistant('Dúvida', {'store': {'whatsapp': '47999991234'}})
        self.assertFalse(enabled)
        self.assertIn('47999991234', reply)


class ChatSessionTests(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        from customers.models import User
        self.tenant = Tenant.objects.create(name='Loja A', subdomain='chat-a')
        self.other = Tenant.objects.create(name='Loja B', subdomain='chat-b')
        self.operator = User.objects.create(tenant=self.tenant, username='chat-a', email='chat-a@example.com', is_staff=True)

    def test_messages_and_handoff_survive_module_reload(self):
        import importlib
        from . import ai_chat
        from .models import ChatMessage, ChatSession
        first = add_chat_message('abc', 'customer', 'Olá', tenant_id=self.tenant.pk)
        second = add_chat_message('abc', 'bot', 'Bem-vindo', tenant_id=self.tenant.pk)
        set_chat_session_mode('abc', 'operator', self.operator.pk, tenant_id=self.tenant.pk)
        importlib.reload(ai_chat)
        self.assertEqual(ChatSession.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.count(), 2)
        state = ensure_chat_session_state('abc', tenant_id=self.tenant.pk)
        self.assertEqual(state['mode'], 'operator')
        self.assertEqual(state['assumido_por'], self.operator.pk)
        self.assertEqual(get_chat_messages('abc', first['id'], tenant_id=self.tenant.pk), [second])
        self.assertEqual(list_active_chat_sessions(self.tenant.pk)[0]['message_count'], 2)
        set_chat_session_mode('abc', 'bot', tenant_id=self.tenant.pk)
        self.assertIsNone(ensure_chat_session_state('abc', tenant_id=self.tenant.pk)['assumido_por'])

    def test_same_session_key_is_isolated_between_tenants(self):
        a = add_chat_message('same', 'customer', 'Loja A', tenant_id=self.tenant.pk)
        b = add_chat_message('same', 'customer', 'Loja B', tenant_id=self.other.pk)
        self.assertEqual(get_chat_messages('same', tenant_id=self.tenant.pk), [a])
        self.assertEqual(get_chat_messages('same', tenant_id=self.other.pk), [b])
        set_chat_session_mode('same', 'operator', self.operator.pk, tenant_id=self.tenant.pk)
        self.assertEqual(ensure_chat_session_state('same', tenant_id=self.other.pk)['mode'], 'bot')
        self.assertEqual(list_active_chat_sessions(self.other.pk)[0]['message_count'], 1)

    def test_operator_idle_for_five_minutes_returns_to_bot(self):
        from .models import ChatMessage

        add_chat_message('idle', 'customer', 'Preciso de ajuda', tenant_id=self.tenant.pk)
        set_chat_session_mode('idle', 'operator', self.operator.pk, tenant_id=self.tenant.pk)
        operator_message = add_chat_message('idle', 'operator', 'Vou verificar', tenant_id=self.tenant.pk)
        ChatMessage.objects.filter(pk=operator_message['id']).update(
            created_at=timezone.now() - timedelta(minutes=6)
        )

        state = reset_idle_operator_session('idle', tenant_id=self.tenant.pk)

        self.assertEqual(state['mode'], 'bot')
        self.assertIsNone(state['assumido_por'])

    def test_missing_tenant_and_foreign_operator_are_rejected(self):
        with self.assertRaises(ValueError):
            ensure_chat_session_state('missing')
        ensure_chat_session_state('foreign', tenant_id=self.other.pk)
        with self.assertRaises(ValueError):
            set_chat_session_mode('foreign', 'operator', self.operator.pk, tenant_id=self.other.pk)
        self.assertFalse(chat_session_belongs_to_tenant('foreign', self.tenant.pk))
        self.assertEqual(get_chat_messages('foreign', tenant_id=self.tenant.pk), [])

    def test_panel_cannot_read_or_change_another_tenants_chat(self):
        from customers.views_auth import painel_bot_mensagens, painel_bot_enviar, painel_bot_alternar_sessao
        from .models import ChatMessage
        add_chat_message('private', 'customer', 'Segredo', tenant_id=self.other.pk)
        factory = RequestFactory()
        for view, request in [
            (painel_bot_mensagens, factory.get('/', {'session_id': 'private'})),
            (painel_bot_enviar, factory.post('/', {'session_id': 'private', 'message': 'Teste'})),
            (painel_bot_alternar_sessao, factory.post('/', {'session_id': 'private'})),
        ]:
            request.user = self.operator
            self.assertEqual(view(request).status_code, 404)
        self.assertEqual(ChatMessage.objects.count(), 1)

    def test_store_messages_are_saved_with_request_tenant(self):
        import json
        from unittest.mock import patch
        from .views import loja_ai_chat
        from .models import ChatMessage
        request = RequestFactory().post('/', data=json.dumps({'session_id': 'store', 'message': 'Olá'}), content_type='application/json')
        request.tenant = self.tenant
        ensure_chat_session_state('store', tenant_id=self.tenant.pk)
        from .models import ChatSession
        ChatSession.objects.filter(tenant=self.tenant, session_key='store').update(introduction_complete=True)
        with patch('core.views.build_store_context', return_value={}), patch('core.views.ask_ai_assistant', return_value=('Resposta de teste', True)):
            response = loja_ai_chat(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(ChatMessage.objects.filter(session__tenant=self.tenant).values_list('sender', flat=True)), ['customer', 'bot'])

    def test_introduction_collects_phone_once(self):
        from .ai_chat import chat_introduction
        from .models import ChatSession
        ensure_chat_session_state('intro', tenant_id=self.tenant.pk)
        context = {'produtos': [{'nome': 'Produto da loja', 'preco': 'R$ 25,00', 'descricao': 'Descrição cadastrada'}]}
        offer = chat_introduction('intro', 'Oi', tenant_id=self.tenant.pk, context=context)
        self.assertIn('Produto da loja por R$ 25,00', offer)
        self.assertNotIn('telefone', offer)
        self.assertIsNone(chat_introduction('intro', 'Outra dúvida', tenant_id=self.tenant.pk, context=context))
        reply = chat_introduction('intro', '(47) 99999-1234', tenant_id=self.tenant.pk)
        self.assertIn('Recebemos seu telefone', reply)
        self.assertIn('logo entraremos em contato', reply)
        self.assertEqual(ChatSession.objects.get(tenant=self.tenant, session_key='intro').customer_phone, '47999991234')
        self.assertIsNone(chat_introduction('intro', 'Qual o endereço?', tenant_id=self.tenant.pk))

    def test_greetings_follow_local_hour(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from .ai_chat import chat_greeting
        for hour, expected in [(8, 'Bom dia'), (12, 'Boa tarde'), (18, 'Boa noite')]:
            with patch('core.ai_chat.timezone.localtime', return_value=SimpleNamespace(hour=hour)):
                self.assertEqual(chat_greeting(), expected)

    def test_close_session_preserves_history_and_blocks_operator_send(self):
        from customers.views_auth import painel_bot_alternar_sessao, painel_bot_enviar
        entry = add_chat_message('close-test', 'customer', 'Olá', tenant_id=self.tenant.pk)
        request = RequestFactory().post('/', {'session_id': 'close-test', 'action': 'encerrar'})
        request.user = self.operator
        self.assertEqual(painel_bot_alternar_sessao(request).status_code, 200)
        self.assertEqual(ensure_chat_session_state('close-test', tenant_id=self.tenant.pk)['mode'], 'closed')
        request = RequestFactory().post('/', {'session_id': 'close-test', 'message': 'Resposta'})
        request.user = self.operator
        self.assertEqual(painel_bot_enviar(request).status_code, 409)
        self.assertEqual(get_chat_messages('close-test', tenant_id=self.tenant.pk), [entry])

    def test_product_details_precede_phone_request(self):
        from .ai_chat import product_details_reply
        reply = product_details_reply([{'nome': 'Produto teste', 'preco': 'R$ 25,00'}], {'store': {'formas_pagamento': ['PIX', 'dinheiro']}})
        self.assertIn('R$ 25,00', reply)
        self.assertIn('PIX', reply)
        self.assertNotIn('telefone', reply)

    def test_panel_rejects_account_on_foreign_tenant_host(self):
        from customers.views_auth import (painel_bot_atendimento, painel_bot_sessoes,
            painel_bot_mensagens, painel_bot_enviar, painel_bot_alternar_sessao)
        add_chat_message('own-session', 'customer', 'Privado', tenant_id=self.tenant.pk)
        for view in [painel_bot_atendimento, painel_bot_sessoes, painel_bot_mensagens, painel_bot_enviar, painel_bot_alternar_sessao]:
            request = RequestFactory().post('/', {'session_id': 'own-session', 'message': 'Teste', 'action': 'encerrar'})
            request.user = self.operator
            request.tenant = self.other
            self.assertEqual(view(request).status_code, 403)
        request = RequestFactory().get('/')
        request.user = self.operator
        request.tenant = self.tenant
        self.assertEqual(painel_bot_sessoes(request).status_code, 200)
        self.assertEqual(ensure_chat_session_state('own-session', tenant_id=self.tenant.pk)['mode'], 'bot')


class HomeTenantRedirectTests(SimpleTestCase):
    def test_root_route_redirects_identified_tenant_without_redirect_middleware(self):
        from types import SimpleNamespace
        from django.urls import resolve
        request = RequestFactory().get('/', HTTP_HOST='andreia.viazap.net')
        request.tenant = SimpleNamespace(id=7, subdomain='andreia')
        response = resolve('/').func(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/loja/')

    def test_main_domain_keeps_landing_page(self):
        from unittest.mock import patch
        from django.http import HttpResponse
        from django.urls import resolve
        request = RequestFactory().get('/', HTTP_HOST='viazap.net')
        request.tenant = None
        with patch('core.views.render', return_value=HttpResponse('home')) as render:
            response = resolve('/').func(request)
        self.assertEqual(response.status_code, 200)
        render.assert_called_once_with(request, 'inicial.html')


class GoogleTagTenantTests(TestCase):
    def setUp(self):
        from tenants.models import Tenant, TenantSettings

        self.first = Tenant.objects.create(name='Analytics A', subdomain='analytics-a')
        self.second = Tenant.objects.create(name='Analytics B', subdomain='analytics-b')
        TenantSettings.objects.create(tenant=self.first, tag_google_analytics='g-1j1vwebse3')
        TenantSettings.objects.create(tenant=self.second, tag_google_analytics='G-OUTRALOJA1')

    def test_context_exposes_only_current_tenant_tag(self):
        from customers.contexto import configuracao_context

        request = RequestFactory().get('/loja/', HTTP_HOST='analytics-a.localhost')
        request.tenant = self.first
        context = configuracao_context(request)
        self.assertEqual(context['ga_measurement_id'], 'G-1J1VWEBSE3')
        self.assertEqual(context['gtm_container_id'], '')

    def test_google_tag_partial_renders_tag_once(self):
        from django.template.loader import render_to_string

        html = render_to_string('loja/includes/google_tag_head.html', {
            'ga_measurement_id': 'G-1J1VWEBSE3',
            'gtm_container_id': '',
        })
        self.assertEqual(html.count('gtag/js?id=G-1J1VWEBSE3'), 1)
        self.assertEqual(html.count("gtag('config', 'G-1J1VWEBSE3')"), 1)


class AITokenUsageTests(TestCase):
    def test_usage_is_accumulated_and_isolated_by_tenant(self):
        from unittest.mock import Mock, patch
        from django.test import override_settings
        from tenants.models import Tenant
        from .ai_chat import ask_ai_assistant, get_ai_token_usage
        first = Tenant.objects.create(name='Tokens A', subdomain='tokens-a')
        second = Tenant.objects.create(name='Tokens B', subdomain='tokens-b')
        response = Mock()
        response.json.return_value = {
            'model': 'test-model',
            'choices': [{'message': {'content': 'Olá'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'total_tokens': 120},
        }
        with override_settings(AI_CHAT_API_KEY='test'), patch('core.ai_chat.requests.post', return_value=response):
            ask_ai_assistant('Oi', {}, tenant_id=first.pk)
            ask_ai_assistant('Oi', {}, tenant_id=first.pk)
            ask_ai_assistant('Oi', {}, tenant_id=second.pk)
        self.assertEqual(get_ai_token_usage(first.pk), {
            'input_tokens': 200, 'output_tokens': 40, 'total_tokens': 240,
        })
        self.assertEqual(get_ai_token_usage(second.pk)['total_tokens'], 120)

    def test_empty_answer_still_counts_reported_usage(self):
        from unittest.mock import Mock, patch
        from django.test import override_settings
        from tenants.models import Tenant
        from .ai_chat import ask_ai_assistant, get_ai_token_usage
        tenant = Tenant.objects.create(name='Tokens', subdomain='tokens')
        response = Mock()
        response.json.return_value = {
            'choices': [{'message': {'content': ''}}],
            'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10},
        }
        with override_settings(AI_CHAT_API_KEY='test'), patch('core.ai_chat.requests.post', return_value=response):
            ask_ai_assistant('Oi', {}, tenant_id=tenant.pk)
        self.assertEqual(get_ai_token_usage(tenant.pk)['total_tokens'], 10)

    def test_local_fallback_does_not_count_tokens(self):
        from django.test import override_settings
        from tenants.models import Tenant
        from .ai_chat import ask_ai_assistant, get_ai_token_usage
        tenant = Tenant.objects.create(name='Tokens', subdomain='tokens')
        with override_settings(AI_CHAT_API_KEY=''):
            ask_ai_assistant('Oi', {}, tenant_id=tenant.pk)
        self.assertEqual(get_ai_token_usage(tenant.pk)['total_tokens'], 0)


class StoreSegmentTests(SimpleTestCase):
    def test_segment_code_is_translated(self):
        from tenants.models import TenantSettings
        self.assertEqual(TenantSettings(segmento='28').segmento_nome, 'Pet shop')
        self.assertEqual(TenantSettings(segmento='1').segmento_nome, 'Alimentação e Bebidas')

    def test_missing_segment_does_not_assume_food_business(self):
        from tenants.models import TenantSettings
        for value in (None, '', '999'):
            self.assertEqual(TenantSettings(segmento=value).segmento_nome, 'Não informado')

    def test_legacy_text_segment_is_preserved(self):
        from tenants.models import TenantSettings
        self.assertEqual(TenantSettings(segmento='Floricultura').segmento_nome, 'Floricultura')


class HandoffPhoneTests(SimpleTestCase):
    def test_unknown_answer_requests_phone(self):
        from .ai_chat import whatsapp_handoff_reply
        self.assertIn('telefone com DDD', whatsapp_handoff_reply({'store': {}}))

    def test_known_phone_is_not_requested_again(self):
        from .ai_chat import whatsapp_handoff_reply
        reply = whatsapp_handoff_reply({'store': {}, 'cliente': {'telefone': '47999991234'}})
        self.assertNotIn('deixe seu telefone', reply)
        self.assertIn('já está registrado', reply)


class ProductSharingTests(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        from menu.models import Produto
        self.a = Tenant.objects.create(name='Loja A', subdomain='alpha')
        self.b = Tenant.objects.create(name='Loja B', subdomain='beta')
        self.product = Produto.objects.create(tenant=self.a, nome='Capacete "A" & ação', price=1234.50,
                                             description='<p>Confortável &amp; seguro</p>', image='produtos/capacete.jpg')
        self.second = Produto.objects.create(tenant=self.a, nome='Segundo', price=0)
        self.other = Produto.objects.create(tenant=self.b, nome='Outro', price=10)

    def render_product(self, tenant, product):
        from django.contrib.auth.models import AnonymousUser
        from tenants.middleware import TenantMiddleware
        from core.views import detalhe
        from django.urls import reverse
        request = RequestFactory().get(reverse('detalhe', args=[product.pk]) + '?tracking=1',
                                       HTTP_HOST=f'{tenant.subdomain}.localhost')
        request.session = {}
        request.user = AnonymousUser()
        return TenantMiddleware(lambda req: detalhe(req, product.pk))(request)

    def metadata(self, response):
        from html.parser import HTMLParser
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.tags = {}
                self.links = {}
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == 'meta':
                    key = attrs.get('property', attrs.get('name'))
                    self.tags.setdefault(key, []).append(attrs.get('content'))
                if tag == 'a' and attrs.get('id'):
                    self.links[attrs['id']] = attrs.get('href')
        parser = Parser()
        parser.feed(response.content.decode())
        return parser

    def test_server_html_and_encoded_whatsapp_message(self):
        from urllib.parse import parse_qs, urlsplit
        response = self.render_product(self.a, self.product)
        self.assertEqual(response.status_code, 200)
        parsed = self.metadata(response)
        tags = parsed.tags
        self.assertEqual(tags['og:title'], [self.product.nome])
        self.assertEqual(tags['og:type'], ['product'])
        self.assertEqual(tags['og:site_name'], ['Loja A'])
        self.assertEqual(tags['og:description'], ['Confortável & seguro — R$ 1.234,50.'])
        self.assertEqual(tags['og:image'], ['https://alpha.localhost/media/produtos/capacete.jpg'])
        self.assertEqual(tags['og:url'], [f'https://alpha.localhost/loja/datail/{self.product.pk}'])
        for field in ('title', 'description', 'image'):
            self.assertEqual(tags['twitter:' + field], tags['og:' + field])
        fallback = urlsplit(parsed.links['shareProductWhatsApp'])
        self.assertContains(response, 'target="_blank" rel="noopener noreferrer"')
        self.assertNotContains(response, 'onclick="compartilharProduto()"')
        self.assertNotContains(response, 'product-share.js')
        self.assertNotContains(response, 'productShareData')
        self.assertEqual(fallback.netloc, 'api.whatsapp.com')
        self.assertEqual(fallback.path, '/send')
        self.assertNotIn('phone', parse_qs(fallback.query))
        message = parse_qs(fallback.query)['text'][0]
        self.assertEqual(message, f'Olha esse produto 👇\n\n{self.product.nome}\nR$ 1.234,50\n\n{tags["og:url"][0]}')
        self.assertContains(response, 'Compartilhar no WhatsApp')

    def test_other_products_no_image_and_no_description(self):
        for tenant, product in [(self.a, self.second), (self.b, self.other)]:
            with self.subTest(tenant=tenant.name):
                tags = self.metadata(self.render_product(tenant, product)).tags
                self.assertEqual(tags['og:title'], [product.nome])
                self.assertTrue(tags['og:image'][0].startswith(f'https://{tenant.subdomain}.localhost/'))
                self.assertIn('_thumb.jpg', tags['og:image'][0])
                self.assertIn(product.nome, tags['og:description'][0])

    def test_cross_tenant_product_is_not_found(self):
        from django.http import Http404
        for tenant, product in [(self.a, self.other), (self.b, self.product)]:
            with self.subTest(tenant=tenant.name), self.assertRaises(Http404):
                self.render_product(tenant, product)

    def test_long_description_is_bounded_and_plain_text(self):
        self.product.description = '<b>' + 'Descrição &amp; detalhes ' * 100 + '</b>'
        self.product.save()
        description = self.metadata(self.render_product(self.a, self.product)).tags['og:description'][0]
        self.assertLessEqual(len(description), 210)
        self.assertNotIn('<b>', description)
        self.assertNotIn('&amp;', description)
        self.assertIn('R$ 1.234,50', description)

    def test_store_image_fallback_and_gallery_priority(self):
        from tenants.models import TenantSettings
        from menu.models import ProdutoImagem
        TenantSettings.objects.create(tenant=self.a, foto_perfil='fotoperfil/loja.jpg')
        tags = self.metadata(self.render_product(self.a, self.second)).tags
        self.assertEqual(tags['og:image'], ['https://alpha.localhost/media/fotoperfil/loja.jpg'])
        ProdutoImagem.objects.create(produto=self.second, imagem='produtos/galeria/foto.jpg')
        tags = self.metadata(self.render_product(self.a, self.second)).tags
        self.assertEqual(tags['og:image'], ['https://alpha.localhost/media/produtos/galeria/foto.jpg'])


class StoreSharingTests(TestCase):
    def test_tenant_store_preview_and_public_metadata(self):
        from tenants.models import Tenant, TenantSettings, Configuracao
        from core.utils import store_share_data
        from django.template.loader import render_to_string
        from urllib.parse import parse_qs, urlsplit
        for subdomain in ('alpha', 'beta'):
            tenant = Tenant.objects.create(name=f'Loja {subdomain}', subdomain=subdomain)
            config = TenantSettings.objects.create(tenant=tenant, descricao_loja='<p>Moda &amp; novidades</p>',
                                                  foto_perfil=f'fotoperfil/{subdomain}.jpg')
            request = RequestFactory().get('/loja/', HTTP_HOST=f'{subdomain}.localhost')
            request.tenant = tenant
            share = store_share_data(request, tenant, config, Configuracao.load())
            self.assertEqual(share['url'], f'https://{subdomain}.localhost/loja/')
            self.assertEqual(share['image'], f'https://{subdomain}.localhost/media/fotoperfil/{subdomain}.jpg')
            self.assertEqual(share['description'], 'Moda & novidades')
            self.assertIn(share['url'], parse_qs(urlsplit(share['whatsapp_url']).query)['text'][0])
            html = render_to_string('loja/index.html', {'store_share': share, 'config': config})
            self.assertIn(f'<meta property="og:image" content="{share["image"]}">', html)
            self.assertEqual(html.count('property="og:description"'), 1)

    def test_panel_shares_user_store_and_rejects_other_tenant(self):
        from tenants.models import Tenant, TenantSettings
        from customers.models import User
        from customers.views_auth import painel_qrcode
        tenant = Tenant.objects.create(name='Minha loja', subdomain='alpha')
        TenantSettings.objects.create(tenant=tenant, foto_perfil='fotoperfil/alpha.jpg', descricao_loja='Minha descrição')
        user = User.objects.create(username='sharing', tenant=tenant)
        request = RequestFactory().get('/painel/qrcode', HTTP_HOST='alpha.localhost')
        request.user = user
        request.tenant = tenant
        request.session = {'tenant_subdomain': 'outro'}
        response = painel_qrcode(request)
        self.assertContains(response, 'Divulgação')
        self.assertContains(response, 'Compartilhar loja no WhatsApp')
        self.assertContains(response, 'https://alpha.localhost/media/fotoperfil/alpha.jpg')
        self.assertContains(response, 'https://alpha.localhost/loja/')
        self.assertContains(response, 'Minha descrição')
        request.tenant = Tenant.objects.create(name='Outra', subdomain='beta')
        self.assertEqual(painel_qrcode(request).status_code, 403)


class StoreCustomerIsolationTests(TestCase):
    def setUp(self):
        from tenants.models import Tenant
        from customers.models import Cliente
        self.a = Tenant.objects.create(name='A', subdomain='alpha')
        self.b = Tenant.objects.create(name='B', subdomain='beta')
        self.phone = '21990921092'
        self.foreign = Cliente.objects.create(tenant=self.b, nome='Outro cliente', telefone=self.phone)

    def context(self, phone):
        from unittest.mock import patch
        from django.contrib.auth.models import AnonymousUser
        from core.views import loja
        request = RequestFactory().get('/loja/')
        request.tenant = self.a
        request.user = AnonymousUser()
        request.session = {}
        if phone is not None:
            request.COOKIES['telefone_cliente'] = phone
        with patch('core.views.render') as render:
            loja(request)
        return render.call_args.kwargs['context']

    def test_cookie_of_other_tenant_does_not_identify_customer(self):
        context = self.context(self.phone)
        self.assertIsNone(context['dados_cliente'])
        self.assertEqual(context['ordens_pendentes'], 0)

    def test_same_phone_selects_current_tenant_and_only_its_orders(self):
        from customers.models import Cliente
        from orders.models import Ordem
        local = Cliente.objects.create(tenant=self.a, nome='Cliente local', telefone=self.phone)
        Ordem.objects.create(tenant=self.a, cliente=local, completo=False)
        Ordem.objects.create(tenant=self.a, cliente=local, completo=True)
        Ordem.objects.create(tenant=self.b, cliente=local, completo=False)
        context = self.context(self.phone)
        self.assertEqual(context['dados_cliente'], local)
        self.assertEqual(context['ordens_pendentes'], 1)

    def test_missing_or_unknown_cookie_keeps_anonymous_greeting(self):
        for phone in (None, '', '00000000000'):
            with self.subTest(phone=phone):
                context = self.context(phone)
                self.assertIsNone(context['dados_cliente'])
                self.assertEqual(context['ordens_pendentes'], 0)
