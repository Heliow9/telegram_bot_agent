# Ajustes de agendamento Bet2026

Este pacote corrige os pontos que impediam/fragilizavam os envios automáticos:

## Corrigido

1. **Pré-análise 30 minutos antes**
   - Antes: buscava somente jogos entre 29 e 31 minutos antes.
   - Agora: busca jogos que começam entre 0 e 30 minutos.
   - Arquivo: `app/services/daily_leagues_service.py`

2. **Grades 08:00, 12:00 e 18:00**
   - Antes: se a API não retornasse jogos no momento exato, o sistema marcava o turno como enviado.
   - Agora: se vier vazio, não marca como enviado, permitindo nova tentativa no próximo ciclo/startup.
   - Arquivo: `app/services/scheduler_service.py`

3. **Live padrão em 120 segundos**
   - O default agora é `120`.
   - Mesmo assim, confirme no `.env`:

```env
LIVE_MONITOR_INTERVAL_SECONDS=120
```

4. **requirements.txt**
   - Corrigido `email-validatorredis` para duas dependências separadas:

```txt
email-validator
redis
```

## Depois de subir no GitHub e puxar no servidor

```bash
cd /var/www/telegram_bot_agent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
pm2 restart api scheduler worker-analysis celery-beat
pm2 status
```

## Limpar flags antigas do dia

Use uma vez depois do deploy se os envios de hoje já foram marcados incorretamente:

```bash
rm -f data/sent_summaries.json
rm -f data/sent_alerts.json
pm2 restart scheduler
```

## Testes manuais

Grade manhã:

```bash
python -c "from app.services.scheduler_service import job_send_morning_summary; job_send_morning_summary()"
```

Grade tarde:

```bash
python -c "from app.services.scheduler_service import job_send_afternoon_summary; job_send_afternoon_summary()"
```

Grade noite:

```bash
python -c "from app.services.scheduler_service import job_send_night_summary; job_send_night_summary()"
```

Pré-análise 30min:

```bash
python -c "from app.services.scheduler_service import job_send_30min_alerts; job_send_30min_alerts()"
```

Se sua função 30min tiver outro nome no log, use:

```bash
grep -R "def job_.*30\|30min" -n app/services/scheduler_service.py
```

## Conferir logs

```bash
pm2 logs scheduler --lines 80
pm2 logs api --lines 40
```
