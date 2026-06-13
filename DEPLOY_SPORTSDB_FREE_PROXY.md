# Deploy rápido — SportsDB Free

```bash
cd /var/www/telegram_bot_agent
git pull
source venv/bin/activate
pip install -r requirements.txt
bash scripts/apply_sportsdb_free_profile.sh
bash scripts/restart_botbet_services.sh
```

Verifique:

```bash
redis-cli ping
pm2 describe worker-analysis
pm2 logs worker-analysis --lines 120
python scripts/sportsdb_free_status.py
```

O `script args` do worker deve conter `-Q analysis`.

Depois de um 429 antigo, aguarde o cooldown antes de usar `--probe`:

```bash
python scripts/sportsdb_free_status.py --probe --date 2026-06-13
```

Status autenticado pela API:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/admin/sportsdb-status
```

Atualizar calendário/ranking manualmente:

```bash
curl -sS -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/admin/send-basketball-ranking
```
