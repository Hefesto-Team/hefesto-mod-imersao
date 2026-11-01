"""O som do jogo pelo estalo que o ouvido do Hefesto já corta, com o lado de onde ele veio.

``jogo.som`` traz ``{t, evento: "estalo", lado, energia}``: a energia é o RMS em fração da escala
cheia, e :data:`ENERGIA_CHEIA` é a força 1. O lado chega como texto (``esquerdo``, ``direito``,
``centro``) ou como a razão ``(R - L) / (R + L)``, que vira texto pela mesma faixa do centro do
Hefesto (:data:`CENTRO`). Todo estalo sai como ``estalo``; o de força :data:`FORTE` sai também como
``estalo_forte``. O ``t`` do estalo segue junto: é ele que pede o recorte ao ``som.tocar``.
"""
from __future__ import annotations

from typing import Any

from sentidos.base import Derivado, Sentido, numero

ENERGIA_CHEIA = 0.5
FORTE = 0.6
CENTRO = 0.25
LADOS = ("esquerdo", "direito", "centro")


def lado_do_estalo(lado: Any) -> str:
    if isinstance(lado, str):
        return lado if lado in LADOS else "centro"
    razao = numero(lado)
    if razao is None:
        return "centro"
    if razao >= CENTRO:
        return "direito"
    if razao <= -CENTRO:
        return "esquerdo"
    return "centro"


class Som(Sentido):
    topico = "sentido.som"
    origens = ("jogo.som",)
    por_controle = False

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        if dados.get("evento", "estalo") != "estalo":
            return []
        energia = numero(dados.get("energia"))
        if energia is None:
            return []
        forca = round(min(1.0, max(0.0, energia / ENERGIA_CHEIA)), 3)
        lado = lado_do_estalo(dados.get("lado"))
        extra: dict[str, Any] = {"lado": lado, "forca": forca}
        marca = numero(dados.get("t"))
        if marca is not None:
            extra["t"] = marca
        saida = [self.evento("estalo", uniq, **extra)]
        if forca >= FORTE:
            saida.append(self.evento("estalo_forte", uniq, **extra))
        return saida
