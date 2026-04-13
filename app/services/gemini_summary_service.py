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

    def _generate(self, prompt: str) -> Optional[str]:
        if not self.client:
            return None

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            text = (response.text or "").strip()
            return text if text else None
        except Exception as e:
            print(f"[GEMINI] Erro ao gerar conteúdo: {e}")
            return None

    def build_result_summary(self, item: dict) -> Optional[str]:
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
        return self._generate(prompt)

    def build_live_goal_summary(self, item: dict) -> Optional[str]:
        prompt = f"""
Você é um narrador analítico de apostas esportivas.
Escreva uma mensagem curta e premium para Telegram, em português do Brasil.

DADOS CONFIRMADOS:
Liga: {item.get('league', 'Jogo')}
Jogo: {item.get('home_team', 'Casa')} x {item.get('away_team', 'Fora')}
Minuto: {item.get('minute', 'N/D')}
Placar atual: {item.get('home_score', 0)} x {item.get('away_score', 0)}
Time que marcou: {item.get('scoring_team', 'N/D')}
Autor do gol: {item.get('scorer', 'não informado')}
Posse casa: {item.get('home_possession', 'N/D')}
Posse fora: {item.get('away_possession', 'N/D')}
Finalizações casa: {item.get('home_shots', 'N/D')}
Finalizações fora: {item.get('away_shots', 'N/D')}
Finalizações no gol casa: {item.get('home_shots_on_target', 'N/D')}
Finalizações no gol fora: {item.get('away_shots_on_target', 'N/D')}

REGRAS:
- Use só os dados informados.
- Não invente assistência, drible, chute de fora, pressão específica ou jogada se isso não foi dado.
- Se o autor do gol não estiver informado, não invente.
- Máximo de 450 caracteres.
- Não use markdown.
- Tom natural, forte e objetivo.
"""
        return self._generate(prompt)

    def build_live_checkpoint_summary(self, item: dict) -> Optional[str]:
        prompt = f"""
Você é um analista de futebol ao vivo para apostas.
Escreva um resumo claro e útil para Telegram, em português do Brasil.

DADOS CONFIRMADOS:
Liga: {item.get('league', 'Jogo')}
Jogo: {item.get('home_team', 'Casa')} x {item.get('away_team', 'Fora')}
Minuto: {item.get('minute', 'N/D')}
Placar: {item.get('home_score', 0)} x {item.get('away_score', 0)}
Posse casa: {item.get('home_possession', 'N/D')}
Posse fora: {item.get('away_possession', 'N/D')}
Finalizações casa: {item.get('home_shots', 'N/D')}
Finalizações fora: {item.get('away_shots', 'N/D')}
Finalizações no gol casa: {item.get('home_shots_on_target', 'N/D')}
Finalizações no gol fora: {item.get('away_shots_on_target', 'N/D')}
Escanteios casa: {item.get('home_corners', 'N/D')}
Escanteios fora: {item.get('away_corners', 'N/D')}
Vermelhos casa: {item.get('home_red_cards', 'N/D')}
Vermelhos fora: {item.get('away_red_cards', 'N/D')}
Sinal live sugerido: {item.get('live_signal', 'neutro')}
Justificativa objetiva do sinal: {item.get('signal_reason', 'sem vantagem clara no momento')}

REGRAS:
- Não invente lances específicos.
- Explique como a partida está se desenhando.
- Diga se existe sinal de observação ou possível entrada live, sem prometer resultado.
- Máximo de 650 caracteres.
- Não use markdown.
- Tom analítico, premium e direto.
"""
        return self._generate(prompt)