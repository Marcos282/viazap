# burger

## Compartilhamento de produtos

A página pública usa a rota existente `/loja/datail/<id>` (grafia preservada).
O produto é consultado pelo ID e pelo tenant identificado no subdomínio.
Open Graph e Twitter Cards são renderizados no servidor, e o botão WhatsApp
é um link HTML para `api.whatsapp.com/send?text=...`, sem telefone de
destinatário e sem dependência de JavaScript. Abre em uma nova aba.

A imagem principal tem prioridade; na ausência dela são usadas galeria,
imagem extra, foto/logo da loja, logo global ou a imagem estática existente.
A descrição é limpa de HTML e limitada a 180 caracteres antes do preço.
`core.utils.product_share_data` concentra os dados para reutilização futura;
não há dependência da Evolution API.

As URLs compartilhadas são HTTPS, inclusive atrás de proxy. Em produção, o
servidor/CDN deve oferecer HTTPS válido e acesso público sem login tanto à
página quanto a `/media/` e aos arquivos estáticos. A configuração Django
para servir mídia em desenvolvimento não substitui essa configuração em
produção. URLs externas de logos/imagens também precisam suportar HTTPS.

Após publicar, verificar a URL de `og:image` sem autenticação e compartilhar
um produto no WhatsApp em celular e desktop. O preview é controlado pelo
WhatsApp e pode ficar em cache após alterações de imagem ou texto.

Testes: `python manage.py test core.tests.ProductSharingTests` (banco de testes
PostgreSQL). A verificação local também pode usar SQLite em memória, criando
as tabelas pelos models com migrations desativadas, pois há migrations do
projeto com SQL específico de PostgreSQL.

## SEO e mensuração por produto

`core/product_metadata.py` é a representação central: título, descrição limpa,
imagem HTTPS, canonical, preço, moeda, disponibilidade, loja, categoria e SKU.
`product_share_data` mantém a interface anterior. HTML SEO, Open Graph, Twitter,
JSON-LD, links de redes e dados do item no Analytics usam essa representação.
Categorias e configurações de outro tenant são rejeitadas ou omitidas.

A URL histórica `/loja/datail/<id>` permanece. A canonical ignora parâmetros de
rastreamento. Produtos com `status=False` ou `exibir=False` retornam 404 na página
pública e saem da vitrine/sitemap. Na ausência de controle de estoque, `InStock`
significa ativo e disponível para venda no catálogo; não representa contagem
física. O cadastro não fornece marca, GTIN ou avaliações: esses dados não são
inventados no JSON-LD.

Cada subdomínio fornece `/sitemap.xml` e `/robots.txt`. O sitemap contém a loja,
as categorias públicas com produtos e os produtos públicos/ativos daquele
tenant. Usa índice paginado acima de 45 mil URLs. Categorias aproveitam a rota
atual `/loja/?categoria_id=...`. Robots bloqueia `/painel/` e `/admin/`, sem
bloquear mídia ou assets; robots não substitui autorização.

`analytics/commerce.py` monta payloads sem nome, telefone, email ou endereço do
cliente. O script `commerce-analytics.js` envia somente ao Measurement ID da
loja; sem configuração não envia eventos. Se houver GTM, envia ao `dataLayer`:
é necessário configurar tags de eventos GA4 no container do tenant.

- `view_item`: abertura da página pública do produto.
- `add_to_cart`: resposta bem-sucedida do backend, quantidade adicionada.
- `begin_checkout`: clique em Comprar ou submissão do formulário WhatsApp na
  sacola (uma vez por carregamento).
- `purchase`: pedido registrado e mostrado na confirmação, não pagamento
  confirmado. Valor dos itens separado do frete. `transaction_id` inclui tenant
  e pedido; sessionStorage evita repetição na mesma aba e GA4 recebe esse ID.
- `share_product`, `click_whatsapp`, `click_facebook`: intenção de compartilhar,
  medida no clique, não confirmação de envio na rede social.
- `copy_product_link`: somente após a área de transferência confirmar a cópia.

Os links de WhatsApp, Facebook e X continuam funcionais sem Analytics/JavaScript.
A cópia oferece seleção manual quando a área de transferência não está disponível.
O carregamento de Analytics segue a configuração existente de cada tenant.

### Publicação e validação

Executar `collectstatic` no fluxo de deploy para incluir o novo JavaScript.
Validar a URL pública no Google Rich Results Test, inspecionar sitemap/robots e
enviar o sitemap de cada subdomínio ao Search Console. Metadados e sitemap
preparam a descoberta; não garantem indexação ou rich results.
No GA4, verificar DebugView/Tempo real; se necessário, cadastrar dimensões
personalizadas para `tenant_id`, `product_id`, `category` e `share_method`.
Testar pedido e carrinho em celular/desktop sem enviar dados de clientes reais.

Testes: `python manage.py test core orders customers tenants analytics whatsapp`
e `node --test analytics/tests_commerce.cjs`. A execução local nesta alteração
usou SQLite em memória com migrations desativadas; as migrations PostgreSQL
existentes não foram modificadas.

### Próximas etapas previstas (sem mudanças de cadastro nesta entrega)

- Central “Divulgar” no painel: consumir `product_metadata`, sempre consultando
  produto pelo tenant autenticado, e reutilizar os links e o preview existentes.
- URLs amigáveis: adicionar slug opcional, estável, associado ao ID/tenant; só
  depois habilitar rota nova e redirect 301 da antiga e atualizar `reverse`
  central/canonical/sitemap. Não regenerar URL a cada alteração do nome.
- `seo_title` e `seo_description`: opcionais, com fallback automático atual.
  Marca e GTIN/EAN devem ser opcionais e validados antes de entrar no schema.
- Relatórios por produto: agregar GA4 pelos IDs de tenant/produto e cruzar com
  pedidos tenant-scoped. Os payloads de `analytics/commerce.py` podem alimentar
  armazenamento próprio futuro; esta entrega não grava um histórico local de
  eventos nem cria métricas retroativas. Cliques não equivalem a envios.
- Meta Pixel, Google Ads, Meta Ads e Merchant Center: campos/credenciais por
  tenant, com autorização no backend. Não compartilhar secrets com páginas
  públicas nem reutilizar configuração do site principal nas lojas.

## Site institucional ViaZap

A home herda `core/templates/institucional/base.html`, separado dos templates
públicos de lojas e produtos. `core/institutional.py` fornece o contexto da
plataforma, com canonical `https://www.viazap.net/` e imagem social estática
1200 × 630. Organization usa somente nome/URL da plataforma e o logo global
quando cadastrado; WebSite é um JSON-LD separado. Não consulta dados de tenants.

O base permite sobrescrever `seo_title`, `seo_description`, `seo_canonical`,
`seo_image`, `seo_robots`, `og_title`, `og_description`, `og_image`, `og_url`,
`og_type`, `twitter_card`, `twitter_title`, `twitter_description`, `twitter_image`
e `structured_data`. Para novas páginas, fornecer `seo` com título/descrição
exclusivos, canonical e imagem compartilhados entre SEO/Open Graph/Twitter.
Na ausência de canonical, usa o domínio institucional com `request.path`, sem
query string. Usar somente para páginas institucionais.

Hoje Planos, Recursos e Como funciona são âncoras na home. Por isso o sitemap
institucional contém apenas `/`; novas páginas públicas devem ser acrescentadas
em `PUBLIC_PATHS` quando existirem. Sitemap/robots dos tenants continuam usando
seus próprios hosts e produtos.

A Google Tag `G-C4BWMDXFPQ` aparece uma vez no base institucional. Eventos:
`sign_up_click` e `tenant_signup_start` ao iniciar o fluxo pelo link de cadastro;
`login_click`; `pricing_view` uma vez quando a seção Planos entra na tela;
`whatsapp_contact_click` em links de WhatsApp, caso estejam presentes.
Não envia URL, telefone, email ou nome nos parâmetros desses eventos.

A imagem social está em `core/assets/institucional/viazap-social.png`, gerada
pelo cartão tipográfico reproduzível `scripts/build_institutional_social.py`.
Não é carregada como imagem visível da home. Publicar com `collectstatic` e
verificar acesso HTTPS à imagem, sitemap e robots após o deploy.
Testes: `python manage.py test core.test_institutional` e
`node --test analytics/tests_institutional.cjs`.
