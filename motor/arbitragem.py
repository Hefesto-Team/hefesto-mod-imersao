"""O mais forte vence: dois pedidos no mesmo controle, canal e lado não somam.

A força de cada canal é a medida da porta (a amplitude no motor e na háptica, a força máxima do
modo no gatilho, o canal mais aceso vezes o brilho na luz, o volume no som). Com força igual, a
``prioridade`` da regra desempata, e com as duas iguais vence o pedido mais recente.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

Vaga = tuple[str, str, str]


@dataclass(frozen=True)
class Pedido:
    uniq: str
    canal: str
    lado: str
    efeito: str
    forca: float
    prioridade: int
    inicio_ms: float
    regra: int
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def vaga(self) -> Vaga:
        return (self.uniq, self.canal, self.lado)


def _peso(pedido: Pedido) -> tuple[float, int, float, int]:
    return (pedido.forca, pedido.prioridade, pedido.inicio_ms, pedido.regra)


def decidir(pedidos: Iterable[Pedido]) -> dict[Vaga, Pedido]:
    """O vencedor de cada vaga ``(uniq, canal, lado)``."""
    vencedores: dict[Vaga, Pedido] = {}
    for pedido in pedidos:
        atual = vencedores.get(pedido.vaga)
        if atual is None or _peso(pedido) > _peso(atual):
            vencedores[pedido.vaga] = pedido
    return vencedores
