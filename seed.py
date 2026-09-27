# seed.py
import os
import django
import random

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "burger.settings")
django.setup()

from tenants.models import Tenant
from customers.models import Cliente
from menu.models import Category, Produto
from orders.models import Ordem, OrdemItem

def run():
    tenants_list = ["andre", "outro", "teste"]

    for t in tenants_list:
        # Criar ou obter tenant
        tenant, _ = Tenant.objects.get_or_create(
            subdomain=t,
            defaults={"name": f"Tenant {t}"}
        )

        print(f"\n🌐 Populando tenant: {tenant.subdomain}")

        # Categorias
        categorias = ["Bebidas", "Lanches", "Sobremesas"]
        cat_objs = []
        for nome in categorias:
            cat, _ = Category.objects.get_or_create(
                tenant=tenant,
                name=nome
            )
            cat_objs.append(cat)

        # Produtos
        produtos = [
            ("Coca-Cola", "Bebidas", 6.0),
            ("X-Burger", "Lanches", 15.0),
            ("Sorvete", "Sobremesas", 10.0),
        ]
        prod_objs = []
        for nome, cat_nome, preco in produtos:
            cat = Category.objects.get(tenant=tenant, name=cat_nome)
            prod, _ = Produto.objects.get_or_create(
                tenant=tenant,
                nome=nome,
                defaults={
                    "category": cat,
                    "price": preco
                }
            )
            prod_objs.append(prod)

        # Clientes e ordens
        for i in range(1, 3):
            cliente, _ = Cliente.objects.get_or_create(
                email=f"user{i}@{tenant.subdomain}.com",
                defaults={
                    "nome": f"Cliente {i} {tenant.subdomain}",
                    "senha": "1234",
                    "genero": "M",
                    "tenant": tenant,  # muito importante
                }
            )

            # Criar ordem se não existir
            ordem, _ = Ordem.objects.get_or_create(
                tenant=tenant,
                cliente=cliente,
                completo=False
            )

            # Itens da ordem
            for _ in range(2):
                produto = random.choice(prod_objs)
                OrdemItem.objects.get_or_create(
                    tenant=tenant,
                    produto=produto,
                    ordem=ordem,
                    defaults={"quantidade": random.randint(1, 3)}
                )

        print(f"✅ Dados criados para {tenant.subdomain}")

if __name__ == "__main__":
    run()
    print("\n🎉 População concluída!")