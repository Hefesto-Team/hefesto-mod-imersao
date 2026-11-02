"""A impressão de um som: as bandas do estalo, normalizadas e guardadas em bytes, sem o áudio.

A impressão é um vetor de ``bandas × quadros`` números de 0 a 255 em base64 (até
:data:`~receita.formato.TETO_DA_IMPRESSAO` bytes). Ela reconhece um estalo quando o cosseno entre
as bandas dele e o vetor passa do ``limiar`` dela. Nenhuma amostra de áudio entra nem sai daqui:
só a energia por banda que o ``jogo.som`` já publica.
"""
from __future__ import annotations

import base64
import math
from collections.abc import Sequence
from typing import Any

LIMIAR_PADRAO = 0.9


def normalizar(bandas: Sequence[float]) -> list[float]:
    """As bandas divididas pela maior, de 0 a 1; um som mudo vira zeros."""
    teto = max((abs(float(b)) for b in bandas), default=0.0)
    if teto <= 0 or not math.isfinite(teto):
        return [0.0] * len(bandas)
    return [abs(float(b)) / teto for b in bandas]


def cosseno(a: Sequence[float], b: Sequence[float]) -> float:
    """O cosseno entre dois vetores do mesmo tamanho; 0 quando um deles é mudo."""
    if len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def gravar(bandas: Sequence[float], limiar: float = LIMIAR_PADRAO) -> dict[str, Any]:
    """A impressão das ``bandas`` (um quadro), no formato do sentido da receita."""
    vetor = bytes(round(v * 255) for v in normalizar(bandas))
    return {"bandas": len(vetor), "quadros": 1,
            "vetor": base64.b64encode(vetor).decode("ascii"), "limiar": limiar}


def vetor(impressao: dict[str, Any]) -> list[float]:
    """O vetor guardado, de volta a 0..1."""
    return [b / 255 for b in base64.b64decode(impressao["vetor"])]


def reconhece(impressao: dict[str, Any], bandas: Any) -> bool:
    """Se as ``bandas`` de um estalo são o som da impressão."""
    if not isinstance(bandas, list) or not all(
            isinstance(b, (int, float)) and not isinstance(b, bool) for b in bandas):
        return False
    guardado = vetor(impressao)
    if len(bandas) != len(guardado):
        return False
    return cosseno(normalizar(bandas), guardado) >= impressao.get("limiar", LIMIAR_PADRAO)
