# Fix Radar Future-Only + Scheduler

## O que mudou

- Novo endpoint: `GET /dashboard/opportunities?limit=10&hours=24`
- O radar agora retorna somente jogos:
  - pendentes
  - futuros
  - dentro da janela informada
  - sem `finished_at`
  - sem status resolvido
  - com probabilidade > 0
  - com odd válida > 1
- O score do radar é calculado no backend, não em dados históricos do front.
- `.env.example` ajustado para `LIVE_MONITOR_INTERVAL_SECONDS=120`.

## Deploy no servidor

```bash
cd /var/www/telegram_bot_agent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
rm -f data/sent_summaries.json data/sent_alerts.json
pm2 restart api scheduler worker-analysis celery-beat
pm2 logs api --lines 50
pm2 logs scheduler --lines 100
```

## Teste do novo endpoint

```bash
curl -s https://api-bet2026.duckdns.org/dashboard/opportunities?limit=5\&hours=24 \
  -H "Authorization: Bearer SEU_TOKEN"
```

No front, o radar deve mostrar "Nenhuma oportunidade futura válida" quando não houver jogos futuros com odd/probabilidade, em vez de mostrar jogos antigos.
