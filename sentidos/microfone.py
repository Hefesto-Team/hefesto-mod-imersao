"""O microfone de cada controle, só pelo nível: o silêncio longo e o barulho súbito.

``microfone.nivel`` traz o pico de 0 a 1 de cada controle. O nível abaixo de :data:`SILENCIO` por
mais de :data:`SILENCIO_LONGO_MS` sobe o ``silencio`` até 1 em :data:`SOBE_EM_MS`; o pico que salta
acima de :data:`SUBITO` depois de silêncio é «se mexeu»: sai o evento ``mexeu``, o silêncio
recomeça e o ``sobressalto`` vai a 1 e cai pela metade a cada :data:`MEIA_VIDA_DO_SOBRESSALTO_MS`.
O microfone mudo não dá opinião: aquele controle sai da conta.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sentidos.base import Derivado, Sentido, meia_vida, numero

SILENCIO = 0.05
SUBITO = 0.4
SILENCIO_LONGO_MS = 8000.0
SOBE_EM_MS = 22_000.0
MEIA_VIDA_DO_SOBRESSALTO_MS = 1500.0
CALMO_ANTES = 0.1


class Microfone(Sentido):
    topico = "sentido.microfone"
    origens = ("microfone.nivel",)

    def __init__(self) -> None:
        self.silencio_desde: dict[str, float | None] = {}
        self.ultimo: dict[str, float] = {}
        self.sobressalto_em: float | None = None

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        if uniq is None:
            return []
        nivel = numero(dados.get("nivel"))
        if dados.get("mudo") is True or nivel is None:
            self.silencio_desde.pop(uniq, None)
            self.ultimo.pop(uniq, None)
            return []
        antes = self.ultimo.get(uniq)
        self.ultimo[uniq] = nivel
        if nivel < SILENCIO:
            if self.silencio_desde.get(uniq) is None:
                self.silencio_desde[uniq] = t_ms
            return []
        self.silencio_desde[uniq] = None
        if nivel >= SUBITO and antes is not None and antes < CALMO_ANTES:
            self.sobressalto_em = t_ms
            return [self.evento("mexeu", uniq, forca=round(nivel, 3))]
        return []

    def tique(self, t_ms: float, controles: Iterable[str],
              vibrando: frozenset[str]) -> list[Derivado]:
        silencio = 0.0
        for desde in self.silencio_desde.values():
            if desde is not None:
                silencio = max(silencio, (t_ms - desde - SILENCIO_LONGO_MS) / SOBE_EM_MS)
        sobressalto = 0.0
        if self.sobressalto_em is not None:
            sobressalto = meia_vida(1.0, t_ms - self.sobressalto_em, MEIA_VIDA_DO_SOBRESSALTO_MS)
        return [self.nivel(silencio=silencio, sobressalto=sobressalto)]
