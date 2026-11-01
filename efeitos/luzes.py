"""As cinco luzes de jogador como lado: as duas da ponta acendem, e o número volta depois do prazo.

A barra de luz é um RGB só e não tem lado. O lado na luz usa as luzes de jogador por máscara (o bit
0 é a luz da esquerda) e por prazo, e quem devolve o número do jogador é o Hefesto, ao fim do prazo.
O prazo nunca passa de :data:`PRAZO_MAXIMO_MS`: o número do jogador não some por mais que isso.
"""
from __future__ import annotations

PRAZO_MAXIMO_MS = 600
MASCARAS = {"esquerdo": 0b00011, "direito": 0b11000, "ambos": 0b11011}


def mascara(lado: str) -> int:
    return MASCARAS[lado]


def prazo(dura_ms: float) -> int:
    return int(min(PRAZO_MAXIMO_MS, max(1, round(dura_ms))))
