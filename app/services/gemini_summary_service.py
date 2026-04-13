from typing import Optional
from google import genai
from app.config import settings


class GeminiSummaryService:
    def __init__(self):
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model

        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def is_available(self) -> bool:
        return self.client is not None

    def build_result_summary(self, item: dict) -> Optional[str]:
        if not self.client:
            return None

        home_team = item.get("home_team", "Casa")
        away_team = item.get("away_team", "Fora")
        home_score = item.get("home_score", "-")
        away_score = item.get("away_score", "-")
        pick = item.get("pick", "-")
        real_result = item.get("real_result", "-")
        confidence = item.get("confidence", "-")
        status = item.get("status", "-")
        league = item.get("league", "Jogo")

        prompt = f"""
Você é um assistente de apostas esportivas.
Gere um resumo MUITO curto, em português do Brasil, com no máximo 2 linhas.
Tom: direto, profissional e natural.
Não invente fatos além dos dados abaixo.

Liga: {league}
Jogo: {home_team} x {away_team}
Placar final: {home_score} x {away_score}
Palpite enviado: {pick}
Resultado real: {real_result}
Confiança do modelo: {confidence}
Status do palpite: {status}

Regras:
- Se o palpite acertou, destaque isso de forma breve.
- Se o palpite errou, explique brevemente onde falhou.
- Não use markdown.
- Não use listas.
- Não passe de 220 caracteres.
"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )

            text = (response.text or "").strip()
            return text if text else None

        except Exception as e:
            print(f"[GEMINI] Erro ao gerar resumo: {e}")
            return None