# Deploy - melhoria de coleta futura

Este pacote melhora a coleta de partidas para evitar que o bot dependa apenas de uma data exata da fonte externa.

## Principais mudanças

- `eventsday` por liga + fallback `eventsday` por esporte (`s=Soccer`) com filtro por liga.
- Preload/radar agora usa janela móvel future-only de 48h.
- Pré-live 30min usa janela móvel e não apenas data exata.
- Filtro rígido para descartar jogos passados, finalizados, cancelados/postergados e sem kickoff confiável.
- Logs com motivo do descarte: `date_mismatch`, `past`, `finished`, `league_mismatch`.
- Removido fallback perigoso de temporada inteira para rotina diária, pois ele trazia jogos antigos.

## Comandos no servidor

```bash
cd /var/www/telegram_bot_agent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
redis-cli FLUSHDB
rm -f data/sent_summaries.json data/sent_alerts.json
pm2 restart api scheduler worker-analysis celery-beat
pm2 logs scheduler --lines 120
```

## Testes úteis

```bash
python -c "from app.services.daily_leagues_service import DailyLeaguesService; s=DailyLeaguesService(); print(len(s.get_upcoming_payloads(hours=48)))"
python -c "from app.services.scheduler_service import job_preload_upcoming_predictions; job_preload_upcoming_predictions()"
curl -s "https://api-bet2026.duckdns.org/dashboard/opportunities?limit=10&hours=48" | python3 -m json.tool
```
