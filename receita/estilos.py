"""Os presets do universal por estilo de jogo: o toque que faz sentido em cada um.

O Hefesto diz a chave do estilo do jogo aberto (``jogo.estilo``, a do catálogo dele: ``terror``,
``fps``, ``corrida``...). Cada chave cai num preset, e o preset diz quais efeitos do universal não
tocam (o coração e o alívio, o susto, o impacto nos gatilhos, o peso da mira) e a força do golpe
com lado. Sem estilo, ou com um que o catálogo não tem, vale o preset geral, sem coração e sem
susto. Num Hefesto que não diz o estilo, nada muda: o universal toca inteiro, como o de terror. A
opção ``estilo`` da janela troca o preset à mão; «Pelo jogo» é o padrão. As entradas da janela
continuam valendo por cima: o preset só cala ou suaviza.
"""
from __future__ import annotations

from typing import Any

PELO_JOGO = "Pelo jogo"
OPCAO = "estilo"
TERROR = "Terror"
TIRO = "Tiro"
CORRIDA = "Corrida"
LUTA = "Luta"
AVENTURA = "Aventura"
RITMO = "Ritmo"
GERAL = "Geral"
CORACAO = frozenset({"coracao", "alivio"})  # (noqa-acento)
SUSTO = frozenset({"susto_no_tato", "susto_no_alto_falante"})
IMPACTO = frozenset({"impacto_no_r2", "impacto_no_l2"})
MIRA = frozenset({"peso_da_mira"})
GOLPE = ("motor_esquerdo", "motor_direito")


def _golpe(forca: float) -> dict[str, float]:
    return dict.fromkeys(GOLPE, forca)


PRESETS: dict[str, tuple[frozenset[str], dict[str, float]]] = {
    TERROR: (frozenset(), {}),
    TIRO: (CORACAO | SUSTO | MIRA, {}),
    CORRIDA: (CORACAO | SUSTO | MIRA, _golpe(0.7)),
    LUTA: (CORACAO | SUSTO | MIRA, {}),
    AVENTURA: (CORACAO | SUSTO | MIRA, _golpe(0.5)),
    RITMO: (CORACAO | SUSTO | MIRA | IMPACTO, _golpe(0.6)),
    GERAL: (CORACAO | SUSTO | MIRA, _golpe(0.7)),
}
ESCOLHAS = (PELO_JOGO, *PRESETS)
DO_CATALOGO: dict[str, str] = {
    "terror": TERROR,
    "fps": TIRO,
    "corrida": CORRIDA,
    "simulacao": CORRIDA,
    "luta": LUTA,
    "acao": LUTA,  # (noqa-acento)
    "souls": LUTA,
    "esportes": LUTA,
    "aventura": AVENTURA,
    "plataforma": AVENTURA,
    "furtivo": AVENTURA,
    "retro": AVENTURA,
    "point_and_click": AVENTURA,
    "visual_novel": AVENTURA,
    "maratona": AVENTURA,
    "adulto": AVENTURA,
    "ritmo": RITMO,
}


def preset_do_jogo(estilo: Any) -> str:
    """O preset da chave de estilo que o Hefesto diz; sem ela, ou fora do catálogo, o geral."""
    return DO_CATALOGO.get(estilo, GERAL) if isinstance(estilo, str) else GERAL


def preset(escolha: Any, estilo_do_jogo: Any) -> str:
    """O preset que vale: o escolhido na janela, ou, em «Pelo jogo», o do estilo do jogo."""
    if isinstance(escolha, str) and escolha in PRESETS:
        return escolha
    return preset_do_jogo(estilo_do_jogo)


def do_preset(nome: str) -> tuple[frozenset[str], dict[str, float]]:
    """Os efeitos do universal que não tocam no preset ``nome`` e a escala da força de outros."""
    sem, escalas = PRESETS.get(nome, PRESETS[GERAL])
    return sem, dict(escalas)
