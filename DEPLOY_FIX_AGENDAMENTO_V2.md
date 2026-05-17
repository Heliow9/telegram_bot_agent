# Correção agendamento / pré-live Bet2026

## O que foi corrigido

1. Grades de 08:00, 12:00 e 18:00 agora não incluem jogos já iniciados/finalizados.
2. Catch-up no startup/deploy agora só envia a grade do turno atual, nunca manhã/tarde antigas depois das 18:00.
3. Pré-live continua na janela 0-30 minutos antes do kickoff.
4. Pós-deploy também usa janela 0-30 minutos, para não perder jogos em restart.
5. Chave de alerta pré-live agora inclui a data: `YYYY-MM-DD_fixture_30min`, reduzindo risco de colisão.

## Atualizar servidor

```bash
cd /var/www/telegram_bot_agent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
rm -f data/sent_summaries.json data/sent_alerts.json
pm2 restart api scheduler worker-analysis celery-beat
pm2 logs scheduler --lines 100
```

## Testes manuais

```bash
python -c "from app.services.scheduler_service import job_send_night_summary; job_send_night_summary()"
python -c "from app.services.scheduler_service import job_check_games; job_check_games()"
```

## Logs esperados

- `Catch-up seguro do turno atual`
- `Jogos encontrados na janela dos 30 min:`
- Nunca deve aparecer catch-up de manhã/tarde antigas quando o horário já estiver no turno da noite.
