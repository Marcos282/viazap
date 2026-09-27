#menu/models.py
from django.db import models
from tenants.models import Tenant
from django.utils.text import slugify
import os
import uuid

def _slugify_filename(filename, folder):
    """Monta o caminho salvando o arquivo com nome slugificado (sem acentos/espaços)."""
    nome, ext = os.path.splitext(filename)
    slug = slugify(nome) or 'arquivo'
    return os.path.join(folder, f'{slug}{ext.lower()}')

# Funções top-level (não closures) para que o Django consiga serializá-las nas migrations.
def upload_produto_imagem(instance, filename):
    return _slugify_filename(filename, 'produtos')

def upload_produto_galeria(instance, filename):
    return _slugify_filename(filename, 'produtos/galeria')

def upload_banner(instance, filename):
    return _slugify_filename(filename, 'banners')

# Categoria de produto (lanches, bebidas, etc.)
class Category(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE) # todos os Produtos vinculados a Categoria serao excluidos
    name = models.CharField(max_length=50)
    exibir = models.BooleanField(default=False) # Exibir ou não no menu
    status = models.BooleanField(default=True) # Ativo/Inativo
    ordem = models.IntegerField(default=0) # Ordem de exibição no menu (permite numero negativo))

    def __str__(self):
        return f' {self.name} ({self.tenant})'

# Produtos do cardápio
class Produto(models.Model):
    
    # Pegando o tenant para multi-tenancy
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    nome = models.CharField(max_length=200)
    exibir = models.BooleanField(default=True) # Exibir ou não no menu
    status = models.BooleanField(default=True) # Ativo/Inativo
    
    # Categoria do produto
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    image = models.ImageField(upload_to=upload_produto_imagem, null=True, blank=True)
    imagem_extra = models.ImageField(upload_to=upload_produto_imagem, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    price = models.FloatField()
    digital = models.BooleanField(default=False, null=True, blank=True)
    integrado = models.BooleanField(default=False, null=True, blank=True)
    ordem_exibicao = models.IntegerField(default=0) # Ordem de exibição no menu (permite numero negativo)
    referencia = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):
    
        if not self.referencia:
            self.referencia = f"REF-{uuid.uuid4().int % 1000000}"
        super().save(*args, **kwargs)  

    # Representação em string do produto
    def __str__(self):
        foto = ''
        try:
            foto = self.image.url
        except:
            foto = ''
        return self.nome + " (" + foto + ")"

class ProdutoImagem(models.Model):
    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name='imagens')
    imagem = models.ImageField(upload_to=upload_produto_galeria)
    ordem = models.IntegerField(default=0)

    def __str__(self):
        return f"Imagem de {self.produto.nome} ({self.id})"

    # Propriedade para obter a URL da imagem do produto
    @property
    def imageURL(self):
        try:
            url = self.image.url
        except:
            url = ''
        return url

class Banners(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    titulo = models.CharField(max_length=200)
    descricao = models.TextField(null=True, blank=True)
    banner_pc = models.ImageField(upload_to=upload_banner, null=True, blank=True)
    banner_mobile = models.ImageField(upload_to=upload_banner, null=True, blank=True)
    link = models.URLField(null=True, blank=True)
    ativo = models.BooleanField(default=True)
    ordem_exibicao = models.IntegerField(default=0) # Ordem de exibição no menu (permite numero negativo)

    def __str__(self):
        return self.titulo + " (" + str(self.tenant) + ")"

    @property
    def imageURL(self):
        try:
            url = self.image.url
        except:
            url = ''
        return url