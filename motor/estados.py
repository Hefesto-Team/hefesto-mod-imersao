"""Os estados da cena e os acumuladores: a histerese, o tempo mínimo e a meia-vida."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Estado:
    """Um estado que liga quando o ``quando`` vale e só desliga fora da histerese e depois do
    tempo mínimo ligado."""

    minimo_ms: float = 0.0
    ligado: bool = False
    ligou_em: float = 0.0

    def atualizar(self, t_ms: float, liga: bool, continua: bool) -> bool:
        if not self.ligado:
            if liga:
                self.ligado, self.ligou_em = True, t_ms
        elif not continua and t_ms - self.ligou_em >= self.minimo_ms:
            self.ligado = False
        return self.ligado


def continua_com_histerese(op: str, esquerda: float, direita: float, histerese: float) -> bool:
    """A comparação afrouxada pela histerese: ``x > k`` segue valendo até ``x`` cair a ``k - h``."""
    if op in (">", ">="):
        return esquerda > direita - histerese
    return esquerda < direita + histerese


@dataclass
class Acumulador:
    """Sobe um passo a cada evento e cai pela metade a cada meia-vida, de 0 a 1."""

    passo: float
    meia_vida_ms: float
    valor: float = 0.0
    visto_em: float | None = None

    def atualizar(self, t_ms: float, eventos: int) -> float:
        if self.visto_em is not None and t_ms > self.visto_em:
            self.valor *= 0.5 ** ((t_ms - self.visto_em) / self.meia_vida_ms)
        self.visto_em = t_ms
        self.valor = min(1.0, self.valor + self.passo * eventos)
        return self.valor
