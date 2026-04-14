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
Gere um resumo MUITO curto, em português do Brasil, com no máximo 5 linhas.
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
- Não passe de 660 caracteres.
"""
        return self._generate(prompt)

    def build_live_goal_summary(self, item: dict) -> Optional[str]:
        prompt = f"""
Você é um narrador analítico de futebol ao vivo.
Escreva uma mensagem curta para Telegram, em português do Brasil.

DADOS CONFIRMADOS:
Liga: {item.get('league', 'Jogo')}
Jogo: {item.get('home_team', 'Casa')} x {item.get('away_team', 'Fora')}
Minuto/tempo: {item.get('match_clock', 'N/D')}
Placar atual: {item.get('home_score', 0)} x {item.get('away_score', 0)}
Status da partida: {item.get('status_text', 'N/D')}
Time que marcou: {item.get('scoring_team', 'não identificado')}

REGRAS:
- Use só os dados acima.
- Não invente autor do gol, assistência, drible, pressão, posse ou estatísticas.
- Máximo de 1200 caracteres.
- Não use markdown.

"""
        return self._generate(prompt)

    def build_live_checkpoint_summary(self, item: dict) -> Optional[str]:
        prompt = f"""
Você é um analista de futebol ao vivo.
Gere uma atualização curta para Telegram, em português do Brasil sem linguagem formal.

DADOS CONFIRMADOS:
Liga: {item.get('league', 'Jogo')}
Jogo: {item.get('home_team', 'Casa')} x {item.get('away_team', 'Fora')}
Tempo de jogo: {item.get('match_clock', 'N/D')}
Status: {item.get('status_text', 'N/D')}
Placar: {item.get('home_score', 0)} x {item.get('away_score', 0)}
Leitura do momento: {item.get('live_signal', 'neutro')}
Justificativa objetiva: {item.get('signal_reason', 'sem sinais fortes com os dados disponíveis')}

REGRAS:
- Não invente posse, finalizações, escanteios ou lances.
- Comente apenas o andamento geral com base no placar e status.
- Se os dados forem limitados, mantenha tom prudente.
- Máximo de 1200 caracteres.
- Não use markdown.
"""
        return self._generate(prompt)