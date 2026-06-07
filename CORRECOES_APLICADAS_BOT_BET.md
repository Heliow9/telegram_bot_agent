# Correções aplicadas - Bot Bet 1x2

## Problemas encontrados

1. **Envios duplicados/multiplicados**
   - O projeto permite rodar jobs tanto pelo `web` (`app/main.py`) quanto pelo `scheduler` (`app/worker.py`).
   - As travas antigas (`max_instances=1` e variável `scheduler_started`) só protegem dentro do mesmo processo.
   - Os arquivos `data/sent_alerts.json`, `data/sent_summaries.json`, `data/sent_results.json` e `data/live_state.json` eram lidos e gravados sem lock. Dois processos podiam ler “não enviado” ao mesmo tempo e ambos enviar.

2. **Resumo de turno duplicado**
   - A chave do resumo só era salva depois do envio. Se dois schedulers executassem simultaneamente, os dois enviavam a grade inteira.
   - Agora a chave é “reservada” antes do envio com lock atômico. Se o Telegram falhar, a chave é liberada para tentar de novo.

3. **Pré-live enviado repetido ou depois do início**
   - A validação de janela 0-30 min existia, mas a deduplicação não era atômica entre processos.
   - Agora o alerta 30min é reservado antes do envio com lock atômico.

4. **Live 15/30/45/60 falhando**
   - O `.env` enviado tem `LIVE_MONITOR_INTERVAL_SECONDS=390` (6,5 min). O código aceitava tolerância fixa de 4 min, então podia pular checkpoints.
   - Agora a tolerância acompanha o intervalo configurado. Recomendado usar `LIVE_MONITOR_INTERVAL_SECONDS=60`.

5. **Só aparece 1 jogo**
   - O resumo de turno envia primeiro a “melhor aposta” com 1 jogo, depois ranking/top e resumos por liga.
   - Se só chega 1 mensagem, geralmente é falha após o primeiro envio, league fora da lista `desired_order`, ou processo duplicado/concorrência quebrando o fluxo.
   - A correção de lock reduz o risco de corrida. Ainda recomendo revisar logs de `format_top_ranking`/Telegram caso o ranking não chegue.

## Arquivos alterados

- `app/services/json_lock_store.py` criado.
- `app/services/scheduler_service.py` atualizado com reserva atômica de alertas, resultados e resumos.
- `app/services/live_state_service.py` atualizado com lock e claim de checkpoint.
- `app/services/live_match_monitor_service.py` atualizado para tolerância dinâmica e claim de checkpoint.
- `.env.example` atualizado para `LIVE_MONITOR_INTERVAL_SECONDS=60`.

## Configuração obrigatória no servidor

Use **apenas um processo scheduler**.

No processo web:

```env
APP_ROLE=web
ENABLE_BACKGROUND_JOBS=false
```

No processo scheduler/worker:

```env
APP_ROLE=scheduler
ENABLE_BACKGROUND_JOBS=true
LIVE_MONITOR_INTERVAL_SECONDS=60
```

Se estiver usando PM2, não rode dois comandos que iniciam scheduler ao mesmo tempo.

Comandos para conferir:

```bash
pm2 list
pm2 logs --lines 100
```

Deve existir só 1 processo responsável pelo scheduler.
