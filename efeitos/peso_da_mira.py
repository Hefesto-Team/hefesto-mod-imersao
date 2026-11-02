"""O peso da mira: o ganho do giroscópio que a receita pede ao Hefesto pelo ``mira.peso``.

O ganho vai de :data:`GANHO_MINIMO` a 1 (1 é a mira de sempre) e anda em degraus de
:data:`DEGRAU`; a Força da janela escala o quanto a mira pesa, e a opção :data:`OPCAO` o liga em
toda receita. Cada pedido vale :data:`PRAZO_MS`: a saída o renova a cada :data:`RENOVA_MS`
enquanto o efeito vale, e quando ele acaba o Hefesto devolve o ganho 1 no prazo, sem pedido.
"""
from __future__ import annotations

from typing import Any

OPCAO = "peso_da_mira"
PADRAO = True
GANHO_MINIMO = 0.3
DEGRAU = 0.05
PRAZO_MS = 800
RENOVA_MS = 500


def ganho(bruto: float, forca: float) -> float:
    """O ganho que sai: o peso da receita (``1 - bruto``) vezes a Força, no degrau mais perto."""
    peso = (1.0 - min(1.0, max(GANHO_MINIMO, bruto))) * min(1.0, max(0.0, forca))
    return round(1.0 - round(peso / DEGRAU) * DEGRAU, 2)


def pesa(valor: float) -> bool:
    return valor < 1.0


def pedido(uniq: str, valor: float) -> dict[str, Any]:
    return {"uniq": uniq, "ganho": valor, "ate_ms": PRAZO_MS}
