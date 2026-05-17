# Ajuste API x Dashboard - Central de Ações e Radar

Este pacote adiciona compatibilidade com a dashboard nova.

## Principal correção

Adicionado endpoint:

```http
GET /dashboard/opportunities?limit=10&hours=24
```

Ele alimenta o Radar de Oportunidades usando somente jogos futuros, pendentes, com odd e probabilidade válidas.

## Aliases administrativos

Além das rotas existentes, foram adicionados aliases para evitar 404 quando a dashboard chamar nomes alternativos:

```http
POST /admin/run-prelive
POST /admin/run-pre-analysis
POST /admin/check-results
POST /admin/audit-today
POST /admin/post-deploy-sync
```

## Deploy no servidor

```bash
cd /var/www/telegram_bot_agent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
pm2 restart api scheduler worker-analysis celery-beat
pm2 logs api --lines 50
```

## Testes rápidos

Com token válido da dashboard:

```bash
curl -I https://api-bet2026.duckdns.org/health
```

No navegador:

```text
https://api-bet2026.duckdns.org/docs
```

Confira se aparece `GET /dashboard/opportunities`.
