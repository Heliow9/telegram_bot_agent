Correção Bet2026 - horários, pré-jogo e live

Arquivos alterados:
- app/services/time_utils.py
- app/services/live_match_monitor_service.py
- data/runtime_config.json

O que corrige:
1) Prioriza dateEvent + strTime como UTC e converte para America/Recife.
   Isso evita usar dateEventLocal/strTimeLocal da liga/estádio como se fosse Recife.
2) Monitor live roda a cada 60s e usa checkpoints 15,30,45,60.
3) Se a API não preencher strStatus/intTime, o live infere minuto pelo kickoff local.
4) Checkpoint atrasado não manda 15' aos 31'; manda apenas checkpoint da janela atual.

Como aplicar no servidor:
1. Faça backup:
   cp app/services/time_utils.py app/services/time_utils.py.bak
   cp app/services/live_match_monitor_service.py app/services/live_match_monitor_service.py.bak
   cp data/runtime_config.json data/runtime_config.json.bak

2. Substitua os arquivos pelos deste ZIP.

3. Ajuste o .env para evitar dois schedulers:
   Na API web:
     APP_ROLE=web
     ENABLE_BACKGROUND_JOBS=false
   No worker/scheduler:
     APP_ROLE=scheduler
     ENABLE_BACKGROUND_JOBS=true

4. Reinicie somente um scheduler:
   pkill -f "uvicorn app.main:app" || true
   pkill -f "python -m app.worker" || true
   nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > logs/web.log 2>&1 &
   nohup python -m app.worker > logs/worker.log 2>&1 &

5. Valide:
   tail -f logs/worker.log
   Procure por:
   [SCHEDULER] Iniciado com sucesso.
   [LIVE] Rodando monitor live
   [JOB] START job_check_games
