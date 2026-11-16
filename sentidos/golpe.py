"""O golpe dado: o ataque de quem joga seguido do pulso de vibração do próprio jogo.

O ataque é um botão de ataque (``botoes``) ou um gatilho que passa da metade (``entradas``). Se o
jogo começa a vibrar naquele controle, pelo motor ou pela háptica, em até :data:`JANELA_MS`, o
golpe acertou: sai o evento ``dado`` com o lado e o ``gatilho`` do ataque (``r2``, ``l2`` ou
``nenhum``), para a receita pedir o impacto no gatilho que atacou.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sentidos.base import Derivado, Sentido, numero
from sentidos.rumble import LIMIAR, ORIGENS_DO_JOGO, VibracaoDoJogo

JANELA_MS = 150.0
METADE_DO_GATILHO = 128
ATAQUES = {
    "r2": ("direito", "r2"), "l2": ("esquerdo", "l2"),
    "r1": ("direito", "nenhum"), "l1": ("esquerdo", "nenhum"),
    "square": ("direito", "nenhum"), "triangle": ("direito", "nenhum"),
    "circle": ("direito", "nenhum"),
}


@dataclass
class _Ataque:
    t: float
    lado: str
    gatilho: str


class Golpe(Sentido):
    topico = "sentido.golpe"
    origens = ("botoes", "entradas", *ORIGENS_DO_JOGO)

    def __init__(self) -> None:
        self.jogo = VibracaoDoJogo()
        self.ataques: dict[str, _Ataque] = {}
        self.gatilhos: dict[tuple[str, str], float] = {}
        self.vibrava: dict[str, bool] = {}

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        if uniq is None:
            return []
        if topico == "botoes" and nome == "button.down":
            botao = dados.get("botao", dados.get("button"))
            if isinstance(botao, str) and botao in ATAQUES:
                self._atacou(uniq, t_ms, *ATAQUES[botao])
        elif topico == "entradas":
            for eixo in ("r2", "l2"):
                valor = numero(dados.get(eixo))
                if valor is None:
                    continue
                antes = self.gatilhos.get((uniq, eixo), 0.0)
                self.gatilhos[(uniq, eixo)] = valor
                if valor >= METADE_DO_GATILHO > antes:
                    self._atacou(uniq, t_ms, *ATAQUES[eixo])
        elif topico in ORIGENS_DO_JOGO:
            forca = self.jogo.ler(topico, nome, uniq, dados, t_ms)
            if forca is None:
                return []
            vibra = forca >= LIMIAR
            subiu = vibra and not self.vibrava.get(uniq, False)
            self.vibrava[uniq] = vibra
            ataque = self.ataques.get(uniq)
            if subiu and ataque is not None and t_ms - ataque.t <= JANELA_MS:
                del self.ataques[uniq]
                return [self.evento("dado", uniq, lado=ataque.lado, gatilho=ataque.gatilho,
                                    forca=round(forca, 3))]
        return []

    def tique(self, t_ms: float, controles: Iterable[str],
              vibrando: frozenset[str]) -> list[Derivado]:
        for uniq, vibrava in self.vibrava.items():
            if vibrava:
                self.vibrava[uniq] = self.jogo.forca(uniq, t_ms) >= LIMIAR
        return []

    def _atacou(self, uniq: str, t_ms: float, lado: str, gatilho: str) -> None:
        self.ataques[uniq] = _Ataque(t_ms, lado, gatilho)
