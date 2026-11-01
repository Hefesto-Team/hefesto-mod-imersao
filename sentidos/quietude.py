"""O controle parado: o giro abaixo do limiar por :data:`PARADO_MS` sobe o nível ``quieto``.

A porta só manda ``movimento`` acima da faixa morta, então a ausência de giro também é parada. O
giro sente o próprio motor: enquanto o controle vibra (o rumble e a háptica do jogo, ou a saída da
própria extensão) e por :data:`DEPOIS_DA_VIBRACAO_MS` depois, a leitura do giro não conta.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sentidos.base import Derivado, Sentido, numero
from sentidos.rumble import LIMIAR, nivel_do_jogo

LIMIAR_DO_GIRO = 8.0
PARADO_MS = 2000.0
SOBE_EM_MS = 10_000.0
DEPOIS_DA_VIBRACAO_MS = 100.0
REPETICAO_DA_PORTA_MS = 250.0


class Quietude(Sentido):
    topico = "sentido.quietude"
    origens = ("movimento", "jogo.vibracao", "jogo.haptica")

    def __init__(self) -> None:
        self.mexeu_em: dict[str, float] = {}
        self.vibra_ate: dict[str, float] = {}

    def _vibrou(self, uniq: str, t_ms: float, vibra: bool) -> None:
        fim = t_ms + DEPOIS_DA_VIBRACAO_MS + (REPETICAO_DA_PORTA_MS if vibra else 0.0)
        if vibra or self.vibra_ate.get(uniq, 0.0) > fim:
            self.vibra_ate[uniq] = fim

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        if uniq is None:
            return []
        if topico == "jogo.vibracao":
            par = nivel_do_jogo(dados) if nome != "jogo.fechou" else (0.0, 0.0)
            if par is not None:
                self._vibrou(uniq, t_ms, max(par) >= LIMIAR)
            return []
        if topico == "jogo.haptica":
            par = dados.get("intensidade")
            if isinstance(par, list):
                forcas = [v for v in map(numero, par) if v is not None]
                self._vibrou(uniq, t_ms, bool(forcas) and max(forcas) >= LIMIAR)
            return []
        if t_ms < self.vibra_ate.get(uniq, 0.0):
            return []
        giro = dados.get("giro")
        if not isinstance(giro, dict):
            return []
        eixos = [v for v in map(numero, (giro.get("x"), giro.get("y"), giro.get("z")))
                 if v is not None]
        if eixos and max(abs(v) for v in eixos) >= LIMIAR_DO_GIRO:
            self.mexeu_em[uniq] = t_ms
            return [self.evento("mexeu", uniq)]
        return []

    def tique(self, t_ms: float, controles: Iterable[str],
              vibrando: frozenset[str]) -> list[Derivado]:
        for uniq in vibrando:
            self.vibra_ate[uniq] = max(self.vibra_ate.get(uniq, 0.0),
                                       t_ms + DEPOIS_DA_VIBRACAO_MS)
        quieto = 0.0
        for uniq in controles:
            parado = t_ms - self.mexeu_em.setdefault(uniq, t_ms)
            quieto = max(quieto, (parado - PARADO_MS) / SOBE_EM_MS)
        return [self.nivel(quieto=quieto)]
