"""O catálogo dos efeitos: os padrões PCM da háptica, a tradução do gatilho e a força de cada canal.

O coração e o susto são padrões de onda, não parâmetros de pad: cada padrão é uma lista de golpes
(início, duração, frequência e amplitude), de que saem as amostras PCM para os atuadores e o
envelope que o motor de vibração imita quando a porta ainda não toca háptica. O gatilho fala os
sete modos do console e sai pelos nomes do ``trigger.set`` do Hefesto.
"""
from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from typing import Any

TAXA_DO_PCM = 48_000
BPM_PADRAO = 72.0
DURA_MINIMA_DO_PADRAO_MS = 50.0
DURA_MAXIMA_DO_PADRAO_MS = 4000.0
FORCA_MAXIMA_DO_GATILHO = 8


@dataclass(frozen=True)
class Golpe:
    inicio_ms: float
    dura_ms: float
    frequencia_hz: float
    amplitude: float


@dataclass(frozen=True)
class Padrao:
    golpes: tuple[Golpe, ...]
    repete: bool

    @property
    def dura_ms(self) -> float:
        return max(g.inicio_ms + g.dura_ms for g in self.golpes)


PADROES: dict[str, Padrao] = {
    "coracao": Padrao((Golpe(0, 90, 55, 1.0), Golpe(180, 110, 45, 0.7)), repete=True),  # (noqa-acento)
    "susto": Padrao((Golpe(0, 40, 90, 1.0), Golpe(40, 260, 60, 0.6)), repete=False),
    "estalo": Padrao((Golpe(0, 30, 120, 1.0),), repete=False),
}


def padrao(nome: str, dura_ms: float | None = None) -> Padrao:
    """O padrão do catálogo; o que não se repete, com ``dura_ms``, tem os golpes escalados até ela,
    com a mesma forma."""
    base = PADROES[nome]
    if dura_ms is None or base.repete:
        return base
    alvo = min(DURA_MAXIMA_DO_PADRAO_MS, max(DURA_MINIMA_DO_PADRAO_MS, float(dura_ms)))
    fator = alvo / base.dura_ms
    if abs(fator - 1.0) < 1e-9:
        return base
    return Padrao(tuple(Golpe(g.inicio_ms * fator, g.dura_ms * fator, g.frequencia_hz, g.amplitude)
                        for g in base.golpes), repete=False)


def golpes(escolhido: Padrao) -> list[list[float]]:
    """Os golpes como o ``haptica.registrar`` os pede."""
    return [[round(g.inicio_ms, 3), round(g.dura_ms, 3), g.frequencia_hz, g.amplitude]
            for g in escolhido.golpes]


def _posicao(padrao: Padrao, decorrido_ms: float, bpm: float) -> float | None:
    if decorrido_ms < 0:
        return None
    if not padrao.repete:
        return decorrido_ms if decorrido_ms < padrao.dura_ms else None
    periodo = 60_000.0 / max(1.0, bpm)
    return decorrido_ms % periodo


def envelope(nome: str, decorrido_ms: float, bpm: float = BPM_PADRAO,
             dura_ms: float | None = None) -> float:
    """A amplitude (0 a 1) do padrão naquele instante: o que o motor imita sem a háptica."""
    escolhido = padrao(nome, dura_ms)
    posicao = _posicao(escolhido, decorrido_ms, bpm)
    if posicao is None:
        return 0.0
    return max((g.amplitude for g in escolhido.golpes
                if g.inicio_ms <= posicao < g.inicio_ms + g.dura_ms), default=0.0)


def pcm(nome: str, dura_ms: float, bpm: float = BPM_PADRAO, forca: float = 1.0,
        taxa: int = TAXA_DO_PCM, escala_ms: float | None = None) -> array[int]:
    """As amostras PCM de 16 bits do padrão, por ``dura_ms``: cada golpe é uma senoide que cai."""
    escolhido = padrao(nome, escala_ms)
    total = int(taxa * dura_ms / 1000)
    saida = array("h", bytes(2 * total))
    for i in range(total):
        posicao = _posicao(escolhido, i * 1000 / taxa, bpm)
        if posicao is None:
            continue
        for golpe in escolhido.golpes:
            dentro = posicao - golpe.inicio_ms
            if 0 <= dentro < golpe.dura_ms:
                queda = math.exp(-3.0 * dentro / golpe.dura_ms)
                onda = math.sin(2 * math.pi * golpe.frequencia_hz * dentro / 1000)
                saida[i] = int(32767 * forca * golpe.amplitude * queda * onda)
                break
    return saida


def _byte_da_forca(forca: int) -> int:
    return round(forca * 255 / FORCA_MAXIMA_DO_GATILHO)


def para_o_trigger_set(efeito: dict[str, Any]) -> tuple[str, list[int]]:
    """O nome e os parâmetros do ``trigger.set`` para um efeito de gatilho já validado."""
    modo = efeito["modo"]
    if modo == "resistencia":  # (noqa-acento)
        return "Feedback", [efeito["posicao"], efeito["forca"]]
    if modo == "arma":
        return "Weapon", [efeito["inicio"], efeito["fim"], _byte_da_forca(efeito["forca"])]
    if modo == "vibracao":
        return "Vibration", [efeito["posicao"], efeito["amplitude"], efeito["frequencia"]]  # (noqa-acento)
    if modo == "resistencia_por_zona":
        return "MultiPositionFeedback", list(efeito["forcas"])
    if modo == "rampa":
        return "SlopeFeedback", [efeito["inicio"], efeito["fim"], efeito["forca_inicio"],
                                 efeito["forca_fim"]]
    if modo == "vibracao_por_zona":
        return "MultiPositionVibration", [efeito["frequencia"], *efeito["amplitudes"]]  # (noqa-acento)
    return "Off", []


def forca_do_gatilho(efeito: dict[str, Any]) -> float:
    """A força máxima do modo, de 0 a 1: a medida do «mais forte» no gatilho."""
    modo = efeito["modo"]
    if modo in ("resistencia", "arma"):  # (noqa-acento)
        bruto = efeito["forca"]
    elif modo == "vibracao":
        bruto = efeito["amplitude"]
    elif modo == "rampa":
        bruto = max(efeito["forca_inicio"], efeito["forca_fim"])
    elif modo == "resistencia_por_zona":
        bruto = max(efeito["forcas"])
    elif modo == "vibracao_por_zona":
        bruto = max(efeito["amplitudes"])
    else:
        bruto = 0
    return bruto / FORCA_MAXIMA_DO_GATILHO


def rgb(cor: str) -> list[int]:
    return [int(cor[i:i + 2], 16) for i in (1, 3, 5)]


def forca_da_luz(cor: str, brilho: float) -> float:
    """O canal mais aceso vezes o brilho, de 0 a 1."""
    return max(rgb(cor)) / 255 * brilho


_FORCAS_DO_GATILHO = ("forca", "amplitude", "forca_inicio", "forca_fim")
_ZONAS_DO_GATILHO = ("forcas", "amplitudes")


def gatilho_na_escala(efeito: dict[str, Any], escala: float) -> dict[str, Any]:
    """O efeito de gatilho com as forças vezes ``escala`` (a Força da janela); a força que o modo
    exige fica em 1 no mínimo, e a zona vazia segue vazia."""
    if escala >= 1.0:
        return efeito
    novo = dict(efeito)
    for campo in _FORCAS_DO_GATILHO:
        if campo in novo:
            novo[campo] = max(1, round(novo[campo] * escala))
    for campo in _ZONAS_DO_GATILHO:
        if campo in novo:
            novo[campo] = [round(v * escala) for v in novo[campo]]
    return novo
