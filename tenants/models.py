# tenants/models.py


from django.db import models
from django.core.exceptions import ValidationError
 
class SingletonModel(models.Model):
    """
    Base para models Singleton.
    Garante que só exista um registro.
    """
    class Meta:
        abstract = True
 
    def save(self, *args, **kwargs):
        if not self.pk and self.__class__.objects.exists():
            raise ValidationError("Já existe uma instância desse Singleton.")
        return super().save(*args, **kwargs)
 
    @classmethod  #Esse comando faz da função um metodo para ser chamado no objeto
    def load(cls):
        """
        Retorna a única instância, ou cria se não existir.
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
 
class Configuracao(SingletonModel):
    nome_empresa = models.CharField(max_length=100, default="Minha Empresa")
    email_contato = models.EmailField(default="contato@empresa.com")
    telefone = models.CharField(max_length=20, blank=True, null=True)

    @property
    def telefone_numero(self):
        """Telefone geral somente com dígitos, pronto para links wa.me."""
        numero = ''.join(char for char in (self.telefone or '') if char.isdigit())
        if len(numero) in (10, 11):
            numero = f'55{numero}'
        return numero
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    dominio= models.CharField(max_length=100, default="meusite.com")
    favicon = models.ImageField(upload_to="favicons/", blank=True, null=True)
    valor_mensalidade = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    Token_mercadolivre = models.CharField(max_length=255, blank=True, null=True)
    secret_mercadolivre = models.CharField(max_length=255, blank=True, null=True)
    client_id_mercadolivre = models.CharField(max_length=255, blank=True, null=True)
    SecrectKey = models.CharField(max_length=255, blank=True, null=True)
    dias_gratuitos = models.IntegerField(default=30)
    front_page = models.ImageField(upload_to="front_pages/", blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=10, blank=True, null=True)
    complemento = models.CharField(max_length=255, blank=True, null=True)
    bairro = models.CharField(max_length=255, blank=True, null=True)
    cidade = models.CharField(max_length=255, blank=True, null=True)
    estado = models.CharField(max_length=255, blank=True, null=True)
    cep = models.CharField(max_length=20, blank=True, null=True)
    cnpj = models.CharField(max_length=20, blank=True, null=True)
    inscricao_estadual = models.CharField(max_length=20, blank=True, null=True)
    nome_razao_social = models.CharField(max_length=255, blank=True, null=True)
    logo_footer = models.ImageField(upload_to="logos/", blank=True, null=True)


    def __str__(self):
        return "Configurações do Sistema"


class Tenant(models.Model):
    name = models.CharField(max_length=100)
    subdomain = models.CharField(max_length=50, unique=True)    
    created_at = models.DateTimeField(auto_now_add=True)
    dt_nascimento = models.DateField(null=True, blank=True)
    documento = models.CharField(max_length=20, blank=True, null=True)
    cpf_ou_cnpj = models.CharField(max_length=20, blank=True, null=True)
    nome_responsavel = models.CharField(max_length=100, blank=True, null=True)
    aberto = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    
    def esta_aberto_agora(self, dt=None):
        """Verifica se o tenant está aberto no momento"""
        from datetime import datetime, date
        if dt is None:
            dt = datetime.now()
        
        # Converter dia da semana do Django para o sistema do HorarioFuncionamento
        # Django: 0=segunda, 1=terça, 2=quarta, 3=quinta, 4=sexta, 5=sábado, 6=domingo
        # HorarioFuncionamento: 0=domingo, 1=segunda, 2=terça, 3=quarta, 4=quinta, 5=sexta, 6=sábado
        django_weekday = dt.weekday()  # 0=segunda, 6=domingo
        if django_weekday == 6:  # Se é domingo no Django
            dia_semana = 0  # Domingo no HorarioFuncionamento
        else:
            dia_semana = django_weekday + 1  # Converte: segunda(0)->1, terça(1)->2, etc.
        
        hora_atual = dt.time()
        data_atual = dt.date()
        
        print(f"=== DEBUG ESTA_ABERTO_AGORA ===")
        print(f"Data/Hora: {dt}")
        print(f"Django weekday(): {django_weekday} (0=segunda, 6=domingo)")
        print(f"Dia convertido para HorarioFuncionamento: {dia_semana} (0=domingo, 1=segunda, etc.)")
        print(f"Hora atual: {hora_atual}")
        print(f"Data atual: {data_atual}")
        
        # Primeiro verifica se há horário especial para hoje
        horarios_especiais = self.horarios.filter(
            data_especifica=data_atual,
            ativo=True
        )
        
        print(f"Horários especiais para hoje: {horarios_especiais.count()}")
        for h in horarios_especiais:
            print(f"  - Especial: {h.horario_abre}-{h.horario_fecha}, Ativo: {h.ativo}")
        
        if horarios_especiais.exists():
            resultado = any(h.esta_no_horario(hora_atual) for h in horarios_especiais)
            print(f"Resultado horários especiais: {resultado}")
            return resultado
        
        # Se não há horário especial, verifica horário normal
        horarios_normais = self.horarios.filter(
            dia_semana=dia_semana,
            data_especifica=None,
            ativo=True
        )
        
        print(f"Horários normais para dia {dia_semana}: {horarios_normais.count()}")
        for h in horarios_normais:
            dentro_horario = h.esta_no_horario(hora_atual)
            print(f"  - Normal: {h.horario_abre}-{h.horario_fecha}, Ativo: {h.ativo}, Dentro do horário: {dentro_horario}")
        
        resultado = any(h.esta_no_horario(hora_atual) for h in horarios_normais)
        print(f"Resultado horários normais: {resultado}")
        
        return resultado
    
    def get_horarios_hoje(self, dt=None):
        """Retorna os horários de funcionamento para hoje"""
        from datetime import datetime
        if dt is None:
            dt = datetime.now()
        
        # Converter dia da semana do Django para o sistema do HorarioFuncionamento
        django_weekday = dt.weekday()
        if django_weekday == 6:  # Se é domingo no Django
            dia_semana = 0  # Domingo no HorarioFuncionamento
        else:
            dia_semana = django_weekday + 1  # Converte: segunda(0)->1, terça(1)->2, etc.
            
        data_atual = dt.date()
        
        # Primeiro verifica horários especiais
        horarios_especiais = self.horarios.filter(
            data_especifica=data_atual,
            ativo=True
        ).order_by('horario_abre')
        
        if horarios_especiais.exists():
            return horarios_especiais
        
        # Se não há horários especiais, retorna horários normais
        return self.horarios.filter(
            dia_semana=dia_semana,
            data_especifica=None,
            ativo=True
        ).order_by('horario_abre')
    
    def get_proximo_horario(self, dt=None):
        """Retorna informações sobre quando a loja abrirá novamente"""
        from datetime import datetime, timedelta
        if dt is None:
            dt = datetime.now()
        
        if self.esta_aberto_agora(dt):
            # Se está aberto, encontra quando fecha
            horarios_hoje = self.get_horarios_hoje(dt)
            hora_atual = dt.time()
            
            for horario in horarios_hoje:
                if horario.esta_no_horario(hora_atual):
                    if horario.is_overnight():
                        # Se é overnight, fecha no dia seguinte
                        return {
                            'acao': 'fecha',
                            'horario': horario.horario_fecha,
                            'data': dt.date() + timedelta(days=1)
                        }
                    else:
                        return {
                            'acao': 'fecha',
                            'horario': horario.horario_fecha,
                            'data': dt.date()
                        }
        
        # Se está fechado, encontra quando abre
        # Procura no resto de hoje
        horarios_hoje = self.get_horarios_hoje(dt)
        hora_atual = dt.time()
        
        for horario in horarios_hoje:
            if horario.horario_abre > hora_atual:
                return {
                    'acao': 'abre',
                    'horario': horario.horario_abre,
                    'data': dt.date()
                }
        
        # Se não abre mais hoje, procura nos próximos 7 dias
        for i in range(1, 8):
            data_futura = dt.date() + timedelta(days=i)
            django_weekday_futuro = (dt.weekday() + i) % 7
            
            # Converter dia da semana do Django para o sistema do HorarioFuncionamento
            if django_weekday_futuro == 6:  # Se é domingo no Django
                dia_semana_futuro = 0  # Domingo no HorarioFuncionamento
            else:
                dia_semana_futuro = django_weekday_futuro + 1  # Converte
            
            horarios_futuros = self.horarios.filter(
                dia_semana=dia_semana_futuro,
                data_especifica=None,
                ativo=True
            ).order_by('horario_abre')
            
            if horarios_futuros.exists():
                return {
                    'acao': 'abre',
                    'horario': horarios_futuros.first().horario_abre,
                    'data': data_futura
                }
        
        return None

# Configurações específicas do Tenant, como tema, cores, etc. É um Singleton por Tenant.
class TenantSettings(models.Model):
    class TipoOperacao(models.TextChoices):
        DELIVERY = 'delivery', 'Alimentação / Delivery'
        VAREJO = 'varejo', 'Comércio / Venda de produtos'

    tipo_operacao = models.CharField(max_length=20, choices=TipoOperacao.choices, default=TipoOperacao.VAREJO, verbose_name='Fluxo de pedidos')

    SEGMENTOS = {'18': 'Academia e esportes', '1': 'Alimentação e Bebidas', '22': 'Artes e cultura', '14': 'Automotivo', '8': 'Beleza, estética e cuidados', '25': 'Calçados', '7': 'Comércio em Geral', '19': 'Construção civil', '24': 'Educação', '9': 'Eletrônicos e importados', '10': 'Farmácia', '11': 'Imobiliário', '27': 'Infantil', '12': 'Móveis, decorações e utilidades', '13': 'Outros', '28': 'Pet shop', '23': 'Publicidade e marketing', '20': 'Saúde', '21': 'Serviços', '16': 'Sexshop', '26': 'Supermercados', '29': 'Transportadora', '17': 'Turismo e hotelaria', '15': 'Vestuário'}

    @property
    def segmento_nome(self):
        segmento = (self.segmento or '').strip()
        return self.SEGMENTOS.get(segmento, segmento if segmento and not segmento.isdigit() else 'Não informado')

    @property
    def whatsapp_numero(self):
        """Número da loja somente com dígitos, pronto para links wa.me."""
        numero = ''.join(char for char in (self.whatsapp or '') if char.isdigit())
        if len(numero) in (10, 11):
            numero = f'55{numero}'
        return numero

    
    # OBSOLETO: Horários de funcionamento agora são gerenciados pela tabela HorarioFuncionamento
    # TODO: Remover esses campos em uma migração futura
    horario_abre = models.TimeField(default="08:00", help_text="OBSOLETO: Use HorarioFuncionamento")
    horario_fecha = models.TimeField(default="18:00", help_text="OBSOLETO: Use HorarioFuncionamento")

    # OBSOLETO: Dias da semana agora são gerenciados pela tabela HorarioFuncionamento
    # TODO: Remover esse campo em uma migração futura
    dias_funcionamento = models.CharField(
        max_length=20,
        default="0,1,2,3,4,5,6",  # todos os dias por padrão
        help_text="OBSOLETO: Use HorarioFuncionamento. Dias da semana abertos, separados por vírgula. 0=Segunda, 6=Domingo"
    )
    tenant = models.OneToOneField(Tenant, on_delete=models.CASCADE, related_name='settings')
    theme_color = models.CharField(max_length=7, default='#FFFFFF')  # Hex color code
    logo_url = models.URLField(blank=True, null=True)
    support_email = models.EmailField(blank=True, null=True)
    nome_loja = models.CharField(max_length=100, default='Seu nome completo')
    descricao_loja = models.TextField(blank=True, null=True)
    whatsapp = models.CharField(max_length=20, default='21976857525')
    taxa_entrega = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    endereco = models.CharField(max_length=200, blank=True, null=True)
    numero_endereco = models.CharField(max_length=20, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=100, blank=True, null=True)
    cep = models.CharField(max_length=20, blank=True, null=True)
    complemento = models.CharField(max_length=100, blank=True, null=True)
    referencia = models.CharField(max_length=200, blank=True, null=True)
    foto_perfil = models.ImageField(upload_to='fotoperfil/', blank=True, null=True)
    foto_capa = models.ImageField(upload_to='fotocapa/', blank=True, null=True)
    facebook = models.URLField(blank=True, null=True)
    instagram = models.URLField(blank=True, null=True)
    color_theme = models.CharField(max_length=7, default="#DD7B0A")  # Hex color code
    tipo_catalogo = models.CharField(max_length=20, default="grid")  # "grid" ou "list"
    pagamento_minimo = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    debito = models.BooleanField(default=True)
    credito = models.BooleanField(default=True)
    pix = models.BooleanField(default=True)
    dinheiro = models.BooleanField(default=True)
    bandeiras_cartao_debito = models.CharField(max_length=200, blank=True, null=True, help_text="Ex: Visa, MasterCard")
    bandeiras_cartao_credito = models.CharField(max_length=200, blank=True, null=True, help_text="Ex: Visa, MasterCard, Amex")
    chave_pix = models.CharField(max_length=100, blank=True, null=True)
    nome_pix = models.CharField(max_length=100, blank=True, null=True)
    delivery = models.BooleanField(default=True)
    chamar_whatsapp = models.BooleanField(default=True, help_text="Exibe o botão para enviar a sacola pelo WhatsApp")
    googleanalytics = models.CharField(max_length=100, blank=True, null=True, help_text="ID do Google Analytics")
    tag_google_analytics = models.CharField(max_length=100, blank=True, null=True, help_text="Tag do Google Analytics")
    google_analytics_property_id = models.CharField(
        max_length=30,
        blank=True,
        default='',
        help_text="ID numérico da propriedade GA4 usado para consultar relatórios.",
    )
    facebook_pixel = models.CharField(max_length=100, blank=True, null=True, help_text="ID do Facebook Pixel")
    instagram_pixel = models.CharField(max_length=100, blank=True, null=True, help_text="ID do Instagram Pixel")
    
    # Campos adicionais para o formulário
    subdomain = models.CharField(max_length=50, blank=True, null=True, help_text="Subdomínio da loja")
    segmento = models.CharField(max_length=50, blank=True, null=True, help_text="Segmento de negócio")
    exibicao_produtos = models.CharField(max_length=20, default="1", help_text="Tipo de exibição dos produtos")
    tipo_chave_pix = models.CharField(max_length=50, blank=True, null=True, help_text="Tipo da chave PIX")
    bot_ativo_ia = models.BooleanField(default=False, verbose_name='Bot ativo com IA', help_text='Abre o chat automaticamente ao entrar na loja.')
    ai_orientations = models.TextField(
        blank=True,
        default='',
        null=True,
        verbose_name='Orientações para a IA',
        help_text='Instruções adicionais que a IA deve seguir no atendimento.',
    )
    
    # Dados do responsável
    nome_responsavel = models.CharField(max_length=100, blank=True, null=True)
    dt_nascimento = models.DateField(blank=True, null=True)
    cpf_ou_cnpj = models.CharField(max_length=10, default="CPF", choices=[("CPF", "CPF"), ("CNPJ", "CNPJ")])
    documento = models.CharField(max_length=20, blank=True, null=True)
    # NOTA: email e password foram movidos para o modelo User (customers_user)
    # email = models.EmailField(blank=True, null=True)  # REMOVIDO - usar User.email
    # password = models.CharField(max_length=128, blank=True, null=True)  # REMOVIDO - usar User.password (criptografado)
    aberto = models.BooleanField(default=True, help_text="Indica se a loja está aberta ou fechada")
    
    def is_open_now(self, dt=None):
        """
        Retorna True se a loja está aberta no momento (ou no datetime dt).
        Utiliza a tabela HorarioFuncionamento atualizada.
        """
        # Delega para o método atualizado do Tenant
        return self.tenant.esta_aberto_agora(dt)

    def get_hora_fechamento_hoje(self, dt=None):
        """
        Retorna informações sobre quando a loja fecha hoje.
        Utiliza a tabela HorarioFuncionamento atualizada.
        """
        from datetime import datetime
        if dt is None:
            dt = datetime.now()
            
        horarios_hoje = self.tenant.get_horarios_hoje(dt)
        hora_atual = dt.time()
        
        if not horarios_hoje.exists():
            return 'Não abre hoje'
            
        # Procura o horário atual em que a loja está funcionando
        for horario in horarios_hoje:
            if horario.esta_no_horario(hora_atual):
                if horario.is_overnight():
                    # Se é overnight, fecha no dia seguinte
                    from datetime import timedelta
                    return datetime.combine(dt.date() + timedelta(days=1), horario.horario_fecha)
                else:
                    return datetime.combine(dt.date(), horario.horario_fecha)
        
        # Se não está em horário de funcionamento, retorna o próximo horário de fechamento
        proximo = self.tenant.get_proximo_horario(dt)
        if proximo and proximo['acao'] == 'abre':
            # Se vai abrir, simula quando fechará
            horario_abertura = None
            for h in horarios_hoje:
                if h.horario_abre == proximo['horario']:
                    horario_abertura = h
                    break
            
            if horario_abertura:
                if horario_abertura.is_overnight():
                    from datetime import timedelta
                    return datetime.combine(proximo['data'] + timedelta(days=1), horario_abertura.horario_fecha)
                else:
                    return datetime.combine(proximo['data'], horario_abertura.horario_fecha)
        
        return 'Não abre hoje'

    @classmethod
    def load(cls, tenant):
        """
        Retorna a única instância, ou cria se não existir.
        """
        obj, created = cls.objects.get_or_create(tenant=tenant)
        return obj

    def __str__(self):
        return f"Settings for {self.tenant.name}"


class HorarioFuncionamento(models.Model):
    DIAS_SEMANA = [
        (0, 'Domingo'),
        (1, 'Segunda-feira'),
        (2, 'Terça-feira'),
        (3, 'Quarta-feira'),
        (4, 'Quinta-feira'),
        (5, 'Sexta-feira'),
        (6, 'Sábado'),
    ]
    
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='horarios')
    dia_semana = models.IntegerField(choices=DIAS_SEMANA)
    horario_abre = models.TimeField()
    horario_fecha = models.TimeField()
    ativo = models.BooleanField(default=True)
    
    # Campos opcionais para casos especiais
    data_especifica = models.DateField(null=True, blank=True, help_text="Para feriados/eventos específicos")
    descricao = models.CharField(max_length=100, blank=True, help_text="Ex: Feriado, Promoção especial")
    
    class Meta:
        unique_together = ['tenant', 'dia_semana', 'data_especifica']
        ordering = ['dia_semana', 'horario_abre']
        verbose_name = 'Horário de Funcionamento'
        verbose_name_plural = 'Horários de Funcionamento'
    
    def __str__(self):
        dia_nome = dict(self.DIAS_SEMANA)[self.dia_semana]
        if self.data_especifica:
            return f"{self.tenant.name} - {dia_nome} ({self.data_especifica}) - {self.horario_abre}-{self.horario_fecha}"
        return f"{self.tenant.name} - {dia_nome} - {self.horario_abre}-{self.horario_fecha}"
    
    def is_overnight(self):
        """Verifica se o horário atravessa a meia-noite"""
        return self.horario_abre > self.horario_fecha
    
    def esta_no_horario(self, hora_atual):
        """Verifica se uma hora específica está dentro do horário de funcionamento"""
        if self.is_overnight():
            return hora_atual >= self.horario_abre or hora_atual < self.horario_fecha
        else:
            return self.horario_abre <= hora_atual < self.horario_fecha
