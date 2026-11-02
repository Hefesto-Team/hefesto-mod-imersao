"""Os ajustes que são da extensão, não da receita: a Força, para quem vai o golpe, os sentidos e
os canais. Valem para toda receita (a sua, a estudada, a da comunidade e o universal), no tique
seguinte, lidos do mesmo ``opcoes.json`` que a janela grava."""
from __future__ import annotations

from typing import Any

FORCA = "forca_geral"
FORCA_PADRAO = 100.0
PARA_QUEM = "para_quem"
QUEM_LEVOU = "Quem levou"
TODOS = "Todos os controles"
ESCOLHAS_DE_PARA_QUEM = (QUEM_LEVOU, TODOS)

SENTIDOS: dict[str, tuple[tuple[str, ...], bool]] = {
    "sentido_som": (("sentido.som", "jogo.som"), True),
    "sentido_vibracao": (("sentido.rumble",), True),
    "sentido_microfone": (("sentido.microfone", "microfone.nivel"), True),
    "sentido_parado": (("sentido.quietude",), True),
    "sentido_tela": (("sentido.tela", "jogo.tela"), False),
    "sentido_golpe": (("sentido.golpe",), True),
}

CANAIS: dict[str, str] = {
    "canal_haptica": "haptica",
    "canal_motor": "motor",
    "canal_gatilho": "gatilho",
    "canal_luz": "luz",
    "canal_leds": "leds",
    "canal_som": "som",
}

TOPICOS_DA_PORTA_COM_CHAVE: dict[str, tuple[str, bool]] = {
    topico: (ident, padrao)
    for ident, (topicos, padrao) in SENTIDOS.items()
    for topico in topicos if not topico.startswith("sentido.")
}


def ligado(opcoes: dict[str, Any], ident: str, padrao: bool = True) -> bool:
    valor = opcoes.get(ident, padrao)
    return valor if isinstance(valor, bool) else padrao


def forca(opcoes: dict[str, Any]) -> float:
    """A Força, de 0 a 1: multiplica tudo o que a extensão escreve; em 0, nada sai."""
    valor = opcoes.get(FORCA, FORCA_PADRAO)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        valor = FORCA_PADRAO
    return min(1.0, max(0.0, float(valor) / 100.0))


def para_todos(opcoes: dict[str, Any]) -> bool:
    return opcoes.get(PARA_QUEM) == TODOS


def topicos_calados(opcoes: dict[str, Any]) -> frozenset[str]:
    """Os tópicos dos sentidos que a janela desligou: o que vem deles não chega à receita."""
    return frozenset(t for ident, (topicos, padrao) in SENTIDOS.items()
                     if not ligado(opcoes, ident, padrao) for t in topicos)


def canais_calados(opcoes: dict[str, Any]) -> frozenset[str]:
    return frozenset(canal for ident, canal in CANAIS.items() if not ligado(opcoes, ident))


def topico_ligado(topico: str, opcoes: dict[str, Any] | None = None) -> bool:
    """O tópico da porta que só se assina com o sentido dele ligado."""
    ident, padrao = TOPICOS_DA_PORTA_COM_CHAVE.get(topico, ("", True))
    return ligado(opcoes or {}, ident, padrao) if ident else True
