"""O que todo sentido universal tem: o que ele lê da porta e o evento derivado que ele publica."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Derivado:
    """Um evento que o sentido tira do que a porta entregou, no tópico ``sentido.<nome>``."""

    topico: str
    nome: str
    uniq: str | None
    dados: dict[str, Any] = field(default_factory=dict)


class Sentido:
    """Lê os tópicos de ``origens`` e o tempo, e publica eventos e níveis em ``topico``.

    ``ler`` recebe cada evento da porta no tique em que ele chega; ``tique`` roda uma vez por
    tique, com os controles conectados e os que a própria extensão faz vibrar agora.
    """

    topico = ""
    origens: tuple[str, ...] = ()
    por_controle = True

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        return []

    def tique(self, t_ms: float, controles: Iterable[str],
              vibrando: frozenset[str]) -> list[Derivado]:
        return []

    def nivel(self, **valores: float) -> Derivado:
        """O nível da cena inteira, de 0 a 1 em cada campo, sem controle."""
        return Derivado(self.topico, "nivel", None,
                        {k: round(min(1.0, max(0.0, v)), 4) for k, v in valores.items()})

    def evento(self, nome: str, uniq: str | None, **dados: Any) -> Derivado:
        return Derivado(self.topico, nome, uniq, dados)


def meia_vida(valor: float, decorrido_ms: float, meia_vida_ms: float) -> float:
    """O valor que cai pela metade a cada ``meia_vida_ms``."""
    if decorrido_ms <= 0:
        return valor
    return float(valor * 0.5 ** (decorrido_ms / meia_vida_ms))


def numero(valor: Any) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)
