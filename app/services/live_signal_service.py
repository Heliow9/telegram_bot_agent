from typing import Dict, Tuple


class LiveSignalService:
    def evaluate(self, snapshot: Dict) -> Tuple[str, str]:
        home_score = int(snapshot.get("home_score", 0) or 0)
        away_score = int(snapshot.get("away_score", 0) or 0)
        status_text = (snapshot.get("status_text") or "").upper()

        if "HALF" in status_text or "HT" in status_text:
            if home_score > away_score:
                return "casa_favorável", "O mandante vai para o intervalo em vantagem."
            if away_score > home_score:
                return "fora_favorável", "O visitante vai para o intervalo em vantagem."
            return "neutro", "Intervalo com placar equilibrado até aqui."

        if home_score > away_score:
            return "casa_favorável", "O mandante está à frente no placar neste momento."

        if away_score > home_score:
            return "fora_favorável", "O visitante está à frente no placar neste momento."

        return "neutro", "Partida empatada até aqui, sem vantagem clara nos dados disponíveis."