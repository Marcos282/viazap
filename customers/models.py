from django.db import models, router, transaction
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from tenants.models import Tenant

# --- User customizado para multi-tenant ---
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, username=None, **extra_fields):
        if not email:
            raise ValueError('O campo email é obrigatório')

        email = self.normalize_email(email).strip()
        
        # Se não foi fornecido username, usar a parte antes do @ do email
        if not username:
            username = email.split('@')[0]
        username = username.strip()

        if not username:
            raise ValueError('O campo username é obrigatório')
        if self.filter(email__iexact=email).exists():
            raise ValueError('Já existe um usuário com este email.')
        if self.filter(username__iexact=username).exists():
            raise ValueError('Já existe um usuário com este username.')

        # A criação da loja fica no save, junto com a criação do usuário.
        # Um tenant explícito continua permitido para operações administrativas.
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, username=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, username, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        db_table = 'customers_user'
    username = models.CharField(max_length=150, unique=True)  # Mantido para subdomain do tenant
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE)
    email = models.EmailField(unique=True)  # Agora obrigatório e único para login
    email_confirmation_pending = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)
    data_expiracao = models.DateTimeField(null=True, blank=True, help_text="Data limite de acesso (trial ou assinatura)")



    USERNAME_FIELD = 'email'  # Login será feito por email
    REQUIRED_FIELDS = ['username']  # Username será solicitado na criação do superuser

    objects = UserManager()

    def save(self, *args, **kwargs):
        database = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=database):
            if not self.tenant_id:
                tenants = Tenant.objects.using(database)
                if tenants.filter(subdomain__iexact=self.username).exists():
                    raise ValidationError({'username': 'Este subdomínio já está em uso.'})
                self.tenant = tenants.create(subdomain=self.username, name=self.username)
            elif self.tenant.subdomain != self.username:
                self.tenant.subdomain = self.username
                self.tenant.name = self.username
                self.tenant.save(using=database)
            if not self.pk and not self.data_expiracao:
                self.data_expiracao = timezone.now() + timedelta(days=30)
            super().save(*args, **kwargs)

    def estender_expiracao(self, dias=30):
        """Soma `dias` à data de expiração, chamado quando o cliente realiza um pagamento."""
        from core.utils import estender_expiracao
        return estender_expiracao(self, dias)

    def __str__(self):
        return f'{self.username} ({self.tenant.subdomain})'
#customers/models.py
from django.db import models
from tenants.models import Tenant
from django.core.validators import RegexValidator


class Cliente(models.Model):
    # Cada cliente pertence a um tenant específico
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    ENUM_GENERO = [
        ('M', 'Masculino'),
        ('F', 'Feminino')
    ]
    nome = models.CharField(max_length=200)
    senha = models.CharField(max_length=200)
    email = models.CharField(max_length=200)
    genero = models.CharField(choices=ENUM_GENERO, max_length=1, default='M')
    endereco = models.CharField(max_length=200, null=True, blank=True)
    referencia = models.CharField(max_length=200, null=True, blank=True)
    cidade = models.CharField(max_length=200, default='Brasília')
    telefone = models.CharField(max_length=200, null=True, blank=True)
    autenticado = models.BooleanField(default=False)

    def __str__(self):
        return self.nome + " (" + str(self.id) + ")"
    
    # Propriedade para retornar o adjetivo correto com base no gênero
    @property
    def adjetivo(self):
        return 'o' if self.genero == 'M' else 'a'


class EnderecoEntrega(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    # Pega o cliente e a ordem como strings para evitar importações circulares
    cliente = models.ForeignKey("customers.Cliente", on_delete=models.SET_NULL, null=True)
    ordem = models.ForeignKey("orders.Ordem", on_delete=models.SET_NULL, null=True)
    
    endereco = models.CharField(max_length=200, null=False)
    referencia = models.CharField(max_length=200, null=False)
    estado = models.CharField(max_length=2, blank=True, default='')
    cidade = models.CharField(max_length=200, null=False)
    dataHora = models.DateTimeField(auto_now_add=True)
    cep = models.CharField(
    max_length=10,
    default="00000000",
    validators=[RegexValidator(regex='^[0-9-]+$', message='Apenas números e hífen são permitidos.')]
    )
    endereco_bairro = models.CharField(max_length=100, null=True, blank=True)
    endereco_numero = models.CharField(max_length=20, null=True, blank=True)
    endereco_complemento = models.CharField(max_length=100, null=True, blank=True)


    def __str__(self):
        return self.endereco
    class Meta:
        verbose_name = "Endereço de Entrega"
        verbose_name_plural = "Endereços de Entrega"