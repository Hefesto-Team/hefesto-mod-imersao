"""Os sentidos universais: o que a porta entrega vira evento com nome, sem estudo do jogo.

Cada sentido publica no próprio tópico (``sentido.<nome>``), que a receita lê como lê um tópico
da porta. Ler um sentido pede as permissões de todas as origens dele.
"""
from __future__ import annotations

from collections.abc import Iterable

from sentidos.base import Derivado, Sentido
from sentidos.golpe import Golpe
from sentidos.microfone import Microfone
from sentidos.quietude import Quietude
from sentidos.rumble import Rumble
from sentidos.som import Som
from sentidos.tela import Tela

CLASSES: tuple[type[Sentido], ...] = (Som, Rumble, Microfone, Tela, Golpe, Quietude)
ORIGENS: dict[str, tuple[str, ...]] = {c.topico: c.origens for c in CLASSES}
POR_CONTROLE = tuple(c.topico for c in CLASSES if c.por_controle)
GLOBAIS = tuple(c.topico for c in CLASSES if not c.por_controle)
TOPICOS = tuple(ORIGENS)


def criar(topicos: Iterable[str]) -> list[Sentido]:
    """Um sentido vivo para cada tópico de sentido que a receita lê."""
    pedidos = set(topicos)
    return [c() for c in CLASSES if c.topico in pedidos]


def origens(topicos: Iterable[str]) -> set[str]:
    """Os tópicos da porta por trás dos tópicos lidos: o de sentido vira as origens dele."""
    saida: set[str] = set()
    for topico in topicos:
        saida |= set(ORIGENS.get(topico, (topico,)))
    return saida


__all__ = ["CLASSES", "GLOBAIS", "ORIGENS", "POR_CONTROLE", "TOPICOS", "Derivado", "Sentido",
           "criar", "origens"]
