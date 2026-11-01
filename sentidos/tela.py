"""A tela do jogo, quando a porta a entrega: o ``dano`` e o ``flash`` viram ``dano_recente``.

``jogo.tela`` traz cinco números de 0 a 1 da cena inteira. O ``dano`` ou o ``flash`` que passa de
:data:`LIMIAR` sai como evento (``dano``, ``flash``); o ``dano_recente`` é o maior dos dois, e cai
pela metade a cada :data:`MEIA_VIDA_MS` depois que eles baixam.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sentidos.base import Derivado, Sentido, meia_vida, numero

LIMIAR = 0.5
MEIA_VIDA_MS = 2000.0


class Tela(Sentido):
    topico = "sentido.tela"
    origens = ("jogo.tela",)
    por_controle = False

    def __init__(self) -> None:
        self.antes = {"dano": 0.0, "flash": 0.0}
        self.dano = 0.0
        self.dano_em = 0.0

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        saida: list[Derivado] = []
        for campo in ("dano", "flash"):
            valor = numero(dados.get(campo))
            if valor is None:
                continue
            valor = min(1.0, max(0.0, valor))
            if valor >= LIMIAR > self.antes[campo]:
                saida.append(self.evento(campo, None, forca=round(valor, 3)))
            self.antes[campo] = valor
            if valor >= self._dano(t_ms):
                self.dano, self.dano_em = valor, t_ms
        return saida

    def tique(self, t_ms: float, controles: Iterable[str],
              vibrando: frozenset[str]) -> list[Derivado]:
        return [self.nivel(dano_recente=self._dano(t_ms))]

    def _dano(self, t_ms: float) -> float:
        return meia_vida(self.dano, t_ms - self.dano_em, MEIA_VIDA_MS)
