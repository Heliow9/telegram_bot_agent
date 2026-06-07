# Atualização: Copa do Mundo e Amistosos Internacionais

Foram adicionadas duas competições ao fluxo principal do bot:

- Copa do Mundo (`FIFA World Cup`, TheSportsDB league id `4429`, temporada `2026`)
- Amistosos Internacionais (`International Friendlies`, TheSportsDB league id `4562`, temporada `2026`)

Arquivos alterados:

- `app/constants.py`
  - adiciona as novas competições à lista `LEAGUES` usada nos resumos por turno, pré-live, radar e monitoramento live.
  - adiciona aliases para aumentar a chance de localizar jogos mesmo quando a API retorna nomes diferentes.

- `app/services/daily_leagues_service.py`
  - passa a considerar `aliases` no filtro de liga.
  - consulta `eventsday` usando o nome oficial e também os aliases.

- `app/services/live_match_monitor_service.py`
  - passa a buscar jogos live usando o nome oficial e os aliases.

- `app/services/message_formatter.py`
  - adiciona emojis para Copa do Mundo e Amistosos Internacionais.

Observação: se TheSportsDB não devolver odds para essas competições, o bot ainda gera a análise com probabilidades/modelo, mas pode ficar sem cotação de mercado.
