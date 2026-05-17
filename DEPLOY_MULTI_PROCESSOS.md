# Upgrade do Bot Bet 1x2 — motor + múltiplos processos

Este pacote já vem com melhorias para rodar melhor em hospedagem:

- cache com Redis e fallback em memória;
- score final auditável para filtrar entradas fracas;
- suporte a Celery para workers paralelos;
- separação recomendada entre web, scheduler, análise e Telegram;
- logs rotativos em `logs/app.log`;
- scripts prontos em `scripts/`.

## 1. Instalar dependências

```bash
pip install -r requirements.txt
```

## 2. Configurar `.env`

Copie o exemplo:

```bash
cp .env.example .env
nano .env
```

Configure principalmente:

```env
DATABASE_URL=mysql+pymysql://usuario:senha@host:3306/banco
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
FOOTBALL_API_KEY=...
ODDS_API_KEY=...
JWT_SECRET_KEY=uma-chave-forte
```

Para múltiplos processos, use Redis:

```env
REDIS_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
CACHE_ENABLED=true
```

Se a hospedagem não tiver Redis, o app continua rodando com cache em memória, mas a deduplicação entre processos fica menos forte.

## 3. Rodar web/API

```bash
./scripts/start_web.sh
```

Ou manual:

```bash
APP_ROLE=web ENABLE_BACKGROUND_JOBS=false uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

## 4. Rodar scheduler separado

```bash
./scripts/start_scheduler.sh
```

Este processo é quem roda jobs de horários, recuperação e monitoramento. Não rode scheduler em todos os workers web para evitar duplicidade.

## 5. Rodar workers Celery

Análise pesada:

```bash
./scripts/start_celery_analysis.sh
```

Envio Telegram:

```bash
./scripts/start_celery_telegram.sh
```

Comandos manuais:

```bash
celery -A app.workers.celery_app.celery_app worker -Q analysis --loglevel=INFO --concurrency=2
celery -A app.workers.celery_app.celery_app worker -Q telegram --loglevel=INFO --concurrency=1
```

## 6. Configuração recomendada na hospedagem

Use processos separados:

```text
web:       scripts/start_web.sh
scheduler: scripts/start_scheduler.sh
analysis:  scripts/start_celery_analysis.sh
telegram:  scripts/start_celery_telegram.sh
```

Na sua VPS/KingHost, dá para usar `tmux`, `screen`, `supervisor` ou `systemd`.

## 7. Score final de entrada

Agora cada análise recebe:

```json
"signal_score": {
  "score": 0.78,
  "approved": true,
  "reason": "score=0.78, prob=..."
}
```

Ajuste no `.env`:

```env
SIGNAL_MIN_SCORE=0.72
SIGNAL_MIN_PROBABILITY=0.52
VALUE_BET_EDGE=0.05
```

Para ser mais conservador:

```env
SIGNAL_MIN_SCORE=0.78
SIGNAL_MIN_PROBABILITY=0.56
VALUE_BET_EDGE=0.07
```

Para enviar mais sinais:

```env
SIGNAL_MIN_SCORE=0.66
SIGNAL_MIN_PROBABILITY=0.50
VALUE_BET_EDGE=0.03
```

## 8. Git push com auto deploy

No servidor, o caminho mais simples é manter seu script atual de pull/restart e reiniciar estes processos:

```bash
git pull
pip install -r requirements.txt
pkill -f "uvicorn app.main:app" || true
pkill -f "python -m app.worker" || true
pkill -f "celery -A app.workers" || true
nohup ./scripts/start_web.sh > logs/web.out 2>&1 &
nohup ./scripts/start_scheduler.sh > logs/scheduler.out 2>&1 &
nohup ./scripts/start_celery_analysis.sh > logs/celery_analysis.out 2>&1 &
nohup ./scripts/start_celery_telegram.sh > logs/celery_telegram.out 2>&1 &
```

## 9. Verificação rápida

```bash
curl http://127.0.0.1:8000/health
ps aux | grep -E "uvicorn|celery|app.worker"
tail -f logs/app.log
```

## 10. Arquivos adicionados

```text
app/services/cache_service.py
app/services/signal_score_service.py
app/workers/celery_app.py
app/workers/tasks.py
app/core/logging_config.py
scripts/start_web.sh
scripts/start_scheduler.sh
scripts/start_celery_analysis.sh
scripts/start_celery_telegram.sh
```
