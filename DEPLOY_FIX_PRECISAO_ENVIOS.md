# Fix de precisão dos envios 08/12/18 e pré-live 30min

## O que foi corrigido

1. **Trava final antes de enviar no Telegram**
   - Pré-live só envia se o jogo estiver entre 0 e 30 minutos antes do início.
   - Se o jogo já começou, passou, está sem horário válido ou está fora da janela, é descartado.

2. **Trava final nas grades dos turnos**
   - Grades das 08:00, 12:00 e 18:00 só enviam jogos futuros válidos.
   - Se o scheduler reiniciar atrasado, ele não manda mais análise de jogo já iniciado/finalizado.

3. **Horário local correto nas mensagens**
   - O Telegram agora usa `local_date`, `local_time` ou `kickoff_local` do payload.
   - Isso evita confusão entre UTC e horário de Recife/Brasília.

4. **Ranking do turno melhorado**
   - Ranking agora mostra até 10 entradas.
   - As grades continuam enviando melhor aposta, ranking e resumo por liga.

## Como aplicar no servidor

```bash
cd /var/www/telegram_bot_agent

git pull origin main

source venv/bin/activate
pip install -r requirements.txt

redis-cli FLUSHDB
rm -f data/sent_alerts.json data/sent_summaries.json

pm2 restart api scheduler worker-analysis celery-beat
```

## Como validar

```bash
pm2 logs scheduler --lines 160
```

Procure por logs assim:

```text
[PRELIVE][DROP] fora da janela
[GUARD][DROP] jogo já começou ou está muito perto
Jogos encontrados na janela dos 30 min: X | raw=Y
Grade do turno processada
```

## Testes manuais

Grade da manhã:

```bash
python -c "from app.services.scheduler_service import job_send_morning_summary; job_send_morning_summary()"
```

Grade da tarde:

```bash
python -c "from app.services.scheduler_service import job_send_afternoon_summary; job_send_afternoon_summary()"
```

Grade da noite:

```bash
python -c "from app.services.scheduler_service import job_send_night_summary; job_send_night_summary()"
```

Pré-live:

```bash
python -c "from app.services.scheduler_service import job_check_games; job_check_games()"
```

> Importante: o pré-live só deve enviar quando existir jogo entre agora e os próximos 30 minutos.
