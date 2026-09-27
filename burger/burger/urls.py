from customers.views_auth import (
    login_view,
    register_view,
    painel_view,
    painel_pedidos_pendentes_count,
    logout_view,
    painel_home,
    painel_categorias,
    painel_categorias_add,
    painel_categoria_delete,
    painel_categorias_edit,
    painel_produtos,
    painel_produtos_add,
    painel_produto_delete,
    painel_produtos_edit,
    painel_configuracao,
    upload_foto_perfil,
    upload_foto_capa,
    painel_qrcode,
    painel_banners,
    painel_banners_add,
    painel_banners_delete,
    painel_banners_edit,
)
 
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from django.urls import include
from django.conf import settings
from django.conf.urls.static import static
from core.views import (
    loja,
    detalhe,
    add_to_cart,
    sacola,
    checkout,
    remover_do_carrinho_ajax,
    atualizar_carrinho_ajax,
    manifest_json,
    cloudflare_dummy,
    image_placeholder,
    checkout_sucesso,
    home_view,
    inicial,
)

from orders.views import pedido_delivery, cadastro_form
from pagamento import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('loja/', loja, name='loja'),
    path('loja/datail/<int:produto_id>', detalhe, name='detalhe'),
    path('add-to-cart/', add_to_cart, name='add_to_cart'),
    path('loja/sacola', sacola, name='sacola'),
    path('loja/checkout', checkout, name='finalizar_pedido'),
    path('carrinho/remover-ajax/', remover_do_carrinho_ajax, name='remover_do_carrinho_ajax'),
    path('atualizar-carrinho/', atualizar_carrinho_ajax, name='atualizar_carrinho_ajax'),
    path('pedido_delivery/', pedido_delivery, name='pedido_delivery'),
    path('cadastro_form',cadastro_form, name='cadastro_form'),
    path('checkout_sucesso/',checkout_sucesso, name='checkout_sucesso'),
    path('login/', login_view, name='login'),
    path('painel/pedidos', painel_view, name='painel_pedidos'),
    path('painel/pedidos/pendentes-count/', painel_pedidos_pendentes_count, name='painel_pedidos_pendentes_count'),
    path('painel/home/', painel_home, name='painel_home'),
    path('painel/categorias/', painel_categorias, name='painel_categorias'),
    path('painel/categorias/adicionar/', painel_categorias_add, name='painel_categorias_add'),
    path('painel/categorias/deletar/<int:categoria_id>/', painel_categoria_delete, name='painel_categoria_delete'),
    path('painel/categorias/editar/<int:categoria_id>/', painel_categorias_edit, name='painel_categorias_edit'),
    path('painel/produtos/', painel_produtos, name='painel_produtos'),
    path('painel/produtos/adicionar/', painel_produtos_add, name='painel_produtos_add'),
    path('painel/produtos/deletar/<int:produto_id>/', painel_produto_delete, name='painel_produto_delete'),
    path('painel/produtos/editar/<int:produto_id>/', painel_produtos_edit, name='painel_produtos_edit'),
    path('painel/configuracao/', painel_configuracao, name='painel_configuracao'),  # Ajuste conforme necessário
    path('painel/upload-foto-perfil/', upload_foto_perfil, name='upload_foto_perfil'),
    path('painel/upload-foto-capa/', upload_foto_capa, name='upload_foto_capa'),
    path('painel/qrcode', painel_qrcode, name='painel_qrcode'),
    path('painel/banners', painel_banners, name='painel_banners'),
    path('painel/banners/adicionar/', painel_banners_add, name='painel_banners_add'),
    path('painel/banners/deletar/<int:banner_id>/', painel_banners_delete, name='painel_banners_delete'),
    path('painel/banners/editar/<int:banner_id>/', painel_banners_edit, name='painel_banners_edit'),
    path('logout/', logout_view, name='logout'),
    path('register/', register_view, name='register'),
    path('manifest.json', manifest_json, name='manifest'),
    path('loja/manifest.json', manifest_json, name='loja_manifest'),  # Para rotas dentro de /loja/
    # Rotas para lidar com Cloudflare CDN em desenvolvimento
    path('cdn-cgi/<path:path>', cloudflare_dummy, name='cloudflare_dummy'),
    path('loja/cdn-cgi/<path:path>', cloudflare_dummy, name='loja_cloudflare_dummy'),
    path('placeholder.png', image_placeholder, name='image_placeholder'),
    path('home_view/', home_view, name='home_view'),
    # Exibe a página principal (home_view) na raiz em vez de redirecionar para /loja/
    path('', home_view, name='home'),
    path('pagamento/',pagamento.site.urls),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


