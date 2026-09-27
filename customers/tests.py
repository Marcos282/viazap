from django.test import TestCase
from django.urls import reverse

from .forms import UserCreationForm
from .models import User
from tenants.models import Tenant


class TenantSessionContextTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Loja Teste', subdomain='loja-teste')
        self.user = User.objects.create_user(
            email='admin@loja-teste.com',
            username='loja-teste',
            password='senha123',
            tenant=self.tenant,
        )

    def test_login_persists_tenant_id_in_session(self):
        response = self.client.post(
            reverse('login'),
            {'email': 'admin@loja-teste.com', 'password': 'senha123'},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get('tenant_id'), self.tenant.id)

    def test_context_processor_loads_tenant_from_session(self):
        session = self.client.session
        session['tenant_id'] = self.tenant.id
        session.save()

        response = self.client.get(reverse('login'))

        self.assertIn('tenant', response.context)
        self.assertEqual(response.context['tenant'].id, self.tenant.id)

    def test_painel_blocks_authenticated_user_from_other_subdomain(self):
        other_tenant = Tenant.objects.create(name='Outra Loja', subdomain='outra-loja')
        other_user = User.objects.create_user(
            email='admin@outra-loja.com',
            username='outra-loja',
            password='senha123',
            tenant=other_tenant,
        )

        self.client.force_login(other_user)
        response = self.client.get(
            reverse('painel_home'),
            HTTP_HOST='loja-teste.localhost:8000',
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)


class UserCredentialUniquenessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='nessa@example.com',
            username='nessa',
            password='senha123',
        )

    def test_manager_rejeita_username_duplicado(self):
        tenants_before = Tenant.objects.count()

        with self.assertRaisesMessage(
            ValueError,
            'Já existe um usuário com este username.',
        ):
            User.objects.create_user(
                email='outro@example.com',
                username='NESSA',
                password='senha123',
            )

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), tenants_before)

    def test_manager_rejeita_email_duplicado(self):
        tenants_before = Tenant.objects.count()

        with self.assertRaisesMessage(
            ValueError,
            'Já existe um usuário com este email.',
        ):
            User.objects.create_user(
                email='NESSA@example.com',
                username='outro',
                password='senha123',
            )

        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Tenant.objects.count(), tenants_before)

    def test_formulario_informa_username_e_email_duplicados(self):
        form = UserCreationForm(data={
            'username': 'NESSA',
            'email': 'NESSA@example.com',
            'password1': 'senha123',
            'password2': 'senha123',
        })

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['username'], ['Este username já está em uso.'])
        self.assertEqual(form.errors['email'], ['Este email já está em uso.'])


class PasswordFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email='password-test@example.com', username='password-test',
            password='Original!8392Forest',
        )

    def test_registration_rejects_weak_password(self):
        form = UserCreationForm(data={
            'username': 'new-shop', 'email': 'new@example.com',
            'password1': 'a', 'password2': 'a',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('password2', form.errors)

    def test_registration_creates_user_with_confirmation_flag(self):
        from django.core import mail
        with self.settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'):
            response = self.client.post(reverse('register'), {
                'username': 'new-shop',
                'email': 'new@example.com',
                'password1': 'Strong!8392Forest',
                'password2': 'Strong!8392Forest',
            })

        self.assertRedirects(response, reverse('login'))
        user = User.objects.get(email='new@example.com')
        self.assertTrue(user.email_confirmation_pending)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/register/confirm/', mail.outbox[0].body)

    def test_registration_confirmation_activates_account_and_redirects_to_login(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        user = User.objects.create_user(
            email='pending@example.com', username='pending', password='Original!8392Forest',
            email_confirmation_pending=True,
        )
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.get(reverse(
            'confirm_registration', args=[uidb64, token],
        ))

        self.assertRedirects(response, reverse('login'))
        user.refresh_from_db()
        self.assertFalse(user.email_confirmation_pending)

    def test_login_blocks_unconfirmed_account(self):
        User.objects.create_user(
            email='blocked@example.com', username='blocked', password='Original!8392Forest',
            email_confirmation_pending=True,
        )

        response = self.client.post(reverse('login'), {
            'email': 'blocked@example.com', 'password': 'Original!8392Forest',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Confirme seu e-mail antes de entrar')

    def test_reset_form_rejects_weak_mismatched_and_similar_passwords(self):
        from .forms import SetNewPasswordForm
        for first, second in [('a', 'a'), ('Forest!82934', 'different'),
                              ('password-test', 'password-test')]:
            with self.subTest(password=first):
                form = SetNewPasswordForm(
                    {'password1': first, 'password2': second}, user=self.user,
                )
                self.assertFalse(form.is_valid())

    def test_reset_changes_password_and_invalidates_token(self):
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.http import urlsafe_base64_encode
        from django.utils.encoding import force_bytes
        token = default_token_generator.make_token(self.user)
        url = reverse('password_reset_confirm', args=[
            urlsafe_base64_encode(force_bytes(self.user.pk)), token,
        ])
        response = self.client.post(url, {'password1': 'a', 'password2': 'a'})
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original!8392Forest'))
        response = self.client.post(url, {
            'password1': 'Changed!9823Forest', 'password2': 'Changed!9823Forest',
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed!9823Forest'))
        self.assertFalse(default_token_generator.check_token(self.user, token))

    def test_panel_rejects_password_before_saving_email(self):
        from django.test import RequestFactory
        from .views_auth import painel_configuracao
        request = RequestFactory().post('/configuracao/', {
            'password': 'a', 'confirm_password': 'a', 'email': 'changed@example.com',
        })
        request.user = self.user
        response = painel_configuracao(request)
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'password-test@example.com')
        self.assertTrue(self.user.check_password('Original!8392Forest'))

    def test_reset_email_uses_https_behind_trusted_proxy(self):
        from django.core import mail
        with self.settings(
            EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
            SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
        ):
            response = self.client.post(reverse('password_reset_request'),
                {'email': self.user.email}, HTTP_X_FORWARDED_PROTO='https',
                HTTP_HOST='testserver')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('https://testserver/password-reset/', mail.outbox[0].body)


class NewRegistrationTenantIsolationTests(TestCase):
    def setUp(self):
        from tenants.models import TenantSettings
        self.old_tenant = Tenant.objects.create(name='Loja antiga', subdomain='reservada')
        self.old_settings = TenantSettings.objects.create(
            tenant=self.old_tenant, foto_perfil='fotoperfil/antiga.jpg')

    def test_form_rejects_orphan_tenant_case_insensitively(self):
        form = UserCreationForm(data={
            'username': 'RESERVADA', 'email': 'nova@example.com',
            'password1': 'Senha-Forte-83746!', 'password2': 'Senha-Forte-83746!',
        })
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['username'], ['Este subdomínio já está em uso.'])

    def test_manager_and_direct_save_do_not_adopt_old_tenant(self):
        from django.core.exceptions import ValidationError
        for username in ('reservada', 'RESERVADA'):
            with self.subTest(username=username):
                with self.assertRaises(ValidationError):
                    User.objects.create_user(email='nova@example.com', username=username)
                with self.assertRaises(ValidationError):
                    User(email='nova@example.com', username=username).save()
        self.assertFalse(User.objects.exists())
        self.old_settings.refresh_from_db()
        self.assertEqual(self.old_settings.foto_perfil.name, 'fotoperfil/antiga.jpg')

    def test_new_registration_gets_new_tenant_and_empty_photos(self):
        from tenants.models import TenantSettings
        form = UserCreationForm(data={
            'username': 'nova', 'email': 'nova@example.com',
            'password1': 'Senha-Forte-83746!', 'password2': 'Senha-Forte-83746!',
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save(commit=False)
        user.save()
        settings = TenantSettings.load(user.tenant)
        self.assertNotEqual(user.tenant_id, self.old_tenant.pk)
        self.assertFalse(settings.foto_perfil)
        self.assertFalse(settings.foto_capa)

    def test_failed_user_save_does_not_leave_new_tenant(self):
        from django.db import IntegrityError
        User.objects.create_user(email='igual@example.com', username='primeira')
        with self.assertRaises(IntegrityError):
            User(email='igual@example.com', username='segunda').save()
        self.assertFalse(Tenant.objects.filter(subdomain='segunda').exists())
