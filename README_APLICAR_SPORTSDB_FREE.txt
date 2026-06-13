ATUALIZAÇÃO BET2026 — SPORTDB FREE

1) Suba os arquivos para /var/www/telegram_bot_agent ou faça git pull.
2) Entre na pasta:
   cd /var/www/telegram_bot_agent
3) Ative a venv:
   source venv/bin/activate
4) Instale dependências:
   pip install -r requirements.txt
5) Aplique o perfil gratuito no .env:
   bash scripts/apply_sportsdb_free_profile.sh
6) Reinicie somente os serviços do Bet2026:
   bash scripts/restart_botbet_services.sh
7) Confira:
   python scripts/sportsdb_free_status.py
   pm2 logs worker-analysis --lines 120

Após um 429, não aperte o botão repetidamente. O gateway respeita o cooldown
compartilhado e reaproveita cache. Para um teste único:

python scripts/sportsdb_free_status.py --probe --date 2026-06-13

Endpoint autenticado de diagnóstico:
GET /admin/sportsdb-status
