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

    def _pick_label(self, pick: str) -> str:
        if pick == "1":
            return "Casa"
        if pick == "2":
            return "Fora"
        if pick == "X":
            return "Empate"
        return str(pick)

    def _result_label(self, real_result: str, home_team: str, away_team: str) -> str:
        if real_result == "1":
            return f"{home_team} venceu"
        if real_result == "2":
            return f"{away_team} venceu"
        if real_result == "X":
            return "Empate"
        return str(real_result)

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

        pick_label = self._pick_label(str(pick))
        result_label = self._result_label(str(real_result), home_team, away_team)

        status_label = "acertou" if str(status).lower() == "hit" else "errou"

        prompt = f"""
Você é um assistente de apostas esportivas.
Escreva um resumo MUITO curto, em português do Brasil, com no máximo 3 linhas.
Tom: direto, claro, profissional e natural.
Use somente os dados fornecidos.
Não invente fatos.

DADOS CONFIRMADOS:
Liga: {league}
Jogo: {home_team} x {away_team}
Placar final: {home_score} x {away_score}
Palpite enviado: {pick_label} ({pick})
Resultado real: {real_result}
Leitura do resultado real: {result_label}
Confiança do modelo: {confidence}
Status do palpite: {status_label}

REGRAS OBRIGATÓRIAS:
- "1" significa vitória do time da casa.
- "X" significa empate.
- "2" significa vitória do time visitante.
- Nunca interprete "1" ou "2" como quantidade de gols.
- Nunca diga que o modelo acertou placar exato se isso não foi informado.
- Nunca fale em autor do gol, estatísticas ou desempenho além dos dados acima.
- Se o status for "acertou", diga que o modelo acertou o vencedor ou o resultado.
- Se o status for "errou", diga de forma breve que o palpite não correspondeu ao resultado final.
- Não use markdown.
- Não use listas.
- Máximo de 420 caracteres.
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
- Máximo de 300 caracteres.
- Não use markdown.
"""
        return self._generate(prompt)

    def build_live_checkpoint_summary(self, item: dict) -> Optional[str]:
        prompt = f"""
Você é um analista de futebol ao vivo.
Gere uma atualização curta para Telegram, em português do Brasil, com linguagem natural.

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
- Máximo de 300 caracteres.
- Não use markdown.
"""
        return self._generate(prompt)