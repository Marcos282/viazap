# Fluxos de pedidos — ViaZap

Implementação incremental sobre Ordem/OrdemItem, sem duplicar checkout nem tabelas de pedidos.

## Dados antigos

16 pedidos e 18 itens preservados no banco local. Todos os pedidos antigos e as 19 configurações existentes recebem varejo, conforme solicitado. Tenants sem configuração recebem varejo ao criá-la.

10 pedidos foram identificados como entrega, 1 como retirada e 5 como a combinar. `completo=False` vira novo; `completo=True` vira concluído. Pagamentos antigos ficam pendentes, pois não há confirmação registrada de pagamento das compras. Não se inventam horários de conclusão nem histórico anterior. Nenhum dado antigo é excluído.

## Campos

TenantSettings: `tipo_operacao` (delivery/varejo; padrão varejo).

Ordem:
- `status`: novo, confirmado, processando, pronto, enviado, concluido, cancelado.
- `tipo_operacao`: cenário copiado ao criar a ordem; mudanças posteriores da loja não o alteram.
- `tipo_entrega`: entrega, retirada, a_combinar.
- `status_pagamento`: pendente, pago, cancelado, estornado.
- `concluido_em`: data real da conclusão registrada pelo novo fluxo.

HistoricoStatusPedido: ordem, status_anterior, status_novo, alterado_em, usuario, observacao.

Campos antigos mantidos. `completo` sinaliza pedido encerrado (concluído ou cancelado), excluindo cancelados das consultas legadas de pendências. Pagamento é independente.

## Fluxos

- Delivery + entrega: novo → processando → pronto → enviado → concluido.
- Delivery + retirada: novo → processando → pronto → concluido.
- Varejo + entrega: novo → confirmado → processando → pronto → enviado → concluido.
- Varejo + retirada: novo → confirmado → processando → pronto → concluido.
- Cancelamento permitido somente antes de concluir/cancelar.
- A combinar: definir modalidade no detalhe antes de marcar pronto.
- Alteração da modalidade permitida em novo/confirmado/processando.
- Estados terminais não apresentam ação de avanço.
- Varejo usa Separando pedido, Pronto para envio/retirada e Entregue/Retirado.
- Delivery usa Em preparação, Pronto, Saiu para entrega e Concluído.

## Segurança e concorrência

Endpoints do painel verificam autenticação, loja da conta e compatibilidade com o tenant do host. Toda busca por pedido inclui tenant.

Transições usam `transaction.atomic()` e `select_for_update()`. O backend verifica estado esperado e próxima transição; histórico e pedido são gravados na mesma transação. Repetição da mesma ação não duplica histórico.

Pagamento e modalidade têm validação no backend e bloqueio de linha. Formulários POST usam CSRF. Não há envio automático de WhatsApp, cobrança ou estorno financeiro: pagamento é um registro manual separado.

Checkout antigo usa tenant do request e restringe produtos à loja. Criações são atômicas; preços são copiados para OrdemItem. Cálculo do item usa preço histórico mesmo que o produto seja alterado ou removido. O recibo de WhatsApp valida que o pedido da sessão pertence à loja atual.

## Endpoints

Preservados: `/painel/pedidos`, `/painel/pedidos/dados/`, `/painel/pedidos/pendentes-count/`, configuração e rotas de checkout.

Adicionados:
- POST `/painel/pedidos/<id>/status/`: status e status_atual.
- POST `/painel/pedidos/<id>/cancelar/`: status_atual.
- POST `/painel/pedidos/<id>/entrega/`: tipo_entrega.
- POST `/painel/pedidos/<id>/pagamento/`: status_pagamento.
- GET `/painel/pedidos/<id>/historico/`.

WhatsApp usa links e texto centralizado no service. O lojista decide se envia a mensagem. Sem telefone do cliente, não é exibido link inválido.

## Painel e indicadores

Tabela, detalhes e impressão reaproveitados. Configuração Fluxo de pedidos individual por loja.

Indicadores por tenant: novos, em andamento, confirmados, processando, prontos, enviados, concluídos hoje, cancelados e faturamento hoje. Faturamento soma produtos e frete dos pedidos concluídos hoje; não representa caixa nem pagamento confirmado. Conclusões antigas sem data comprovada não entram em hoje.

Polling a cada 10 segundos, sem requisições sobrepostas e pausado quando a aba fica oculta. Modais abertos não são substituídos. Pedidos novos são destacados; alerta sonoro considera somente status novo.

Checkout de entrega continua criando entrega. Pedidos pelo WhatsApp continuam a combinar; o painel permite definir retirada/entrega sem exigir novo checkout.

## Arquivos alterados

- tenants/models.py
- orders/models.py
- orders/views.py
- orders/tests.py
- core/views.py
- customers/views_auth.py
- burger/urls.py
- core/templates/painel/conteudo_configuracao.html
- core/templates/painel/card_pedidos.html
- core/templates/painel/index.html

A edição preexistente do usuário em index.html, removendo o banner de Analytics, foi preservada.

## Arquivos criados

- orders/services/__init__.py
- orders/services/status.py
- orders/services/dashboard.py
- orders/panel_views.py
- core/templates/painel/pedido_indicadores.html
- core/templates/painel/pedido_controles.html
- scripts/test_orders_sqlite.py
- docs/fluxos-pedidos.md

Migrations:
- tenants/0019_tenantsettings_tipo_operacao.py
- orders/0004_ordem_concluido_em_ordem_status_and_more.py
- orders/0005_backfill_order_flow.py

## Validação

- 74 testes aprovados: orders.tests, core.tests e customers.tests.
- Cobertura dos quatro fluxos, isolamento de tenant, host incompatível, POST/CSRF, transições inválidas, estado desatualizado, idempotência, cancelamento, histórico, pagamento independente, snapshot do cenário, indicadores, migração de dados e checkout.
- Execução em SQLite em memória, com schema criado a partir dos models. A função de backfill foi exercitada em teste.
- Migrations reais aplicadas no PostgreSQL local, com conferência dos registros existentes.
- `manage.py check`, `makemigrations --check --dry-run` e `git diff --check`.
- Painel e AJAX renderizados com a conta da loja tor (HTTP 200); JavaScript renderizado passou em `node --check`.
- Navegador indisponível nesta sessão; não houve inspeção visual interativa.
- SQLite testa rejeição de estado desatualizado, mas não o bloqueio concorrente real do PostgreSQL.

Reproduzir sem permissão CREATEDB: `python scripts/test_orders_sqlite.py`.

Em ambiente PostgreSQL de testes com permissão para criar banco: `python manage.py test orders.tests core.tests customers.tests`.

## Produção

Usar o ambiente virtual e executar na pasta que contém manage.py. Pausar processos que criem pedidos durante as migrations, para schema e backfill entrarem juntos.

1. Fazer backup do banco conforme a rotina da instalação.
2. Publicar os arquivos desta implementação.
3. Executar:

```bash
python manage.py check
python manage.py migrate --plan
python manage.py migrate
```

4. Reiniciar Django/Gunicorn pelo gerenciador já utilizado.
5. Conferir Configuração → Fluxo de pedidos e abrir o painel.
6. Conferir pedidos anteriores e fazer um pedido de teste.python manage.py migrate --plan


Não requer Redis, Celery, Channels nem novas dependências. Não houve publicação em produção.
