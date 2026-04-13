from typing import Dict, Tuple
from app.config import settings


def _to_int(value, default=0) -> int:
    try:
        return int(float(str(value).replace("%", "").strip()))
    except (TypeError, ValueError):
        return default


class LiveSignalService:
    def evaluate(self, snapshot: Dict) -> Tuple[str, str]:
        home_shots = _to_int(snapshot.get("home_shots"))
        away_shots = _to_int(snapshot.get("away_shots"))
        home_on = _to_int(snapshot.get("home_shots_on_target"))
        away_on = _to_int(snapshot.get("away_shots_on_target"))
        home_poss = _to_int(snapshot.get("home_possession"))
        away_poss = _to_int(snapshot.get("away_possession"))
        home_red = _to_int(snapshot.get("home_red_cards"))
        away_red = _to_int(snapshot.get("away_red_cards"))

        shots_diff = home_shots - away_shots
        on_target_diff = home_on - away_on
        possession_diff = home_poss - away_poss

        if away_red > home_red:
            return "casa_favorável", "O visitante está com menos jogadores, o que fortalece o cenário para o mandante."

        if home_red > away_red:
            return "fora_favorável", "O mandante está com menos jogadores, o que fortalece o cenário para o visitante."

        if (
            shots_diff >= settings.live_signal_min_shots_diff
            and on_target_diff >= settings.live_signal_min_on_target_diff
            and possession_diff >= settings.live_signal_min_possession_diff
        ):
            return "casa_favorável", "O mandante produz mais volume, finaliza melhor e controla mais a posse."

        if (
            shots_diff <= -settings.live_signal_min_shots_diff
            and on_target_diff <= -settings.live_signal_min_on_target_diff
            and possession_diff <= -settings.live_signal_min_possession_diff
        ):
            return "fora_favorável", "O visitante produz mais volume, finaliza melhor e controla mais a posse."

        if abs(shots_diff) <= 2 and abs(on_target_diff) <= 1 and abs(possession_diff) <= 6:
            return "neutro", "O jogo está equilibrado e ainda não mostra vantagem estatística forte."

        if shots_diff > 0 or on_target_diff > 0:
            return "observação_casa", "O mandante dá sinais de crescimento, mas ainda sem domínio absoluto."

        if shots_diff < 0 or on_target_diff < 0:
            return "observação_fora", "O visitante dá sinais de crescimento, mas ainda sem domínio absoluto."

        return "neutro", "Sem sinais claros de pressão sustentada no momento."