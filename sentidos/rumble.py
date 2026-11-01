"""O rumble do jogo no tempo: pulso curto, rajada e batimento, sem estudo do jogo.

Cada controle tem a vibração que o jogo pede (``jogo.vibracao``, o par ``jogo`` em
``[esq, dir]``). Uma subida acima de :data:`LIMIAR` abre uma batida e a queda a fecha: a batida de
até :data:`PULSO_MS` é um ``pulso``; a que passa disso com força de :data:`FORCA_DA_RAJADA` é uma
``rajada``, e cada rajada sobe o ``dano_recente``. Três subidas seguidas com intervalo de
batimento cardíaco (:data:`BATIMENTO_MS`) são um ``batimento``, que sobe a ``tensao``. A porta
repete o evento a cada 250 ms enquanto vibra; sem a repetição por :data:`SEM_REPETICAO_MS`, a
batida acabou.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from sentidos.base import Derivado, Sentido, meia_vida, numero

LIMIAR = 0.15
PULSO_MS = 150.0
FORCA_DA_RAJADA = 0.4
BATIMENTO_MS = (600.0, 1500.0)
SEM_REPETICAO_MS = 400.0
MEIA_VIDA_DA_TENSAO_MS = 3000.0
MEIA_VIDA_DO_DANO_MS = 4000.0
PASSO_DO_DANO = 0.5


def nivel_do_jogo(dados: dict[str, Any]) -> tuple[float, float] | None:
    """O par ``(esquerdo, direito)`` de 0 a 1 que o jogo pede; ``None`` sem o par."""
    par = dados.get("jogo")
    if isinstance(par, list) and len(par) == 2:
        esq, dir_ = numero(par[0]), numero(par[1])
    else:
        pedido = dados.get("pedido")
        if not isinstance(pedido, list) or len(pedido) != 2:
            return None
        esq, dir_ = numero(pedido[1]), numero(pedido[0])
    if esq is None or dir_ is None:
        return None
    return min(1.0, max(0.0, esq / 255)), min(1.0, max(0.0, dir_ / 255))


@dataclass
class _Batida:
    inicio: float | None = None
    visto: float = 0.0
    pico: float = 0.0
    rajada: bool = False
    subidas: list[float] = field(default_factory=list)


class Rumble(Sentido):
    topico = "sentido.rumble"
    origens = ("jogo.vibracao",)

    def __init__(self) -> None:
        self.batidas: dict[str, _Batida] = {}
        self.tensao = 0.0
        self.batimento_em: float | None = None
        self.dano = 0.0
        self.dano_em = 0.0

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> list[Derivado]:
        if uniq is None:
            return []
        if nome == "jogo.fechou":
            return self._fechar(uniq, t_ms)
        par = nivel_do_jogo(dados)
        if par is None:
            return []
        forca = max(par)
        batida = self.batidas.setdefault(uniq, _Batida())
        if forca < LIMIAR:
            return self._fechar(uniq, t_ms)
        saida: list[Derivado] = []
        batida.visto = t_ms
        if batida.inicio is None:
            batida.inicio, batida.pico, batida.rajada = t_ms, forca, False
            saida += self._subiu(uniq, batida, t_ms, forca)
        batida.pico = max(batida.pico, forca)
        return saida

    def _subiu(self, uniq: str, batida: _Batida, t_ms: float, forca: float) -> list[Derivado]:
        batida.subidas = [t for t in batida.subidas if t_ms - t <= 3 * BATIMENTO_MS[1]]
        batida.subidas.append(t_ms)
        ultimas = batida.subidas[-3:]
        if len(ultimas) == 3 and all(BATIMENTO_MS[0] <= b - a <= BATIMENTO_MS[1]
                                     for a, b in pairwise(ultimas)):
            self.tensao, self.batimento_em = 1.0, t_ms
            return [self.evento("batimento", uniq, forca=round(forca, 3),
                                bpm=round(60_000 / (ultimas[2] - ultimas[1])))]
        return []

    def _fechar(self, uniq: str, t_ms: float) -> list[Derivado]:
        batida = self.batidas.get(uniq)
        if batida is None or batida.inicio is None:
            return []
        dura = t_ms - batida.inicio
        batida.inicio = None
        if dura <= PULSO_MS:
            return [self.evento("pulso", uniq, forca=round(batida.pico, 3), dura_ms=round(dura))]
        return []

    def tique(self, t_ms: float, controles: Iterable[str],
              vibrando: frozenset[str]) -> list[Derivado]:
        saida: list[Derivado] = []
        for uniq, batida in self.batidas.items():
            if batida.inicio is None:
                continue
            if t_ms - batida.visto > SEM_REPETICAO_MS:
                saida += self._fechar(uniq, batida.visto + 250.0)
                continue
            if (not batida.rajada and t_ms - batida.inicio > PULSO_MS
                    and batida.pico >= FORCA_DA_RAJADA):
                batida.rajada = True
                self.dano = min(1.0, self._dano(t_ms) + PASSO_DO_DANO)
                self.dano_em = t_ms
                saida.append(self.evento("rajada", uniq, forca=round(batida.pico, 3)))
        tensao = 0.0
        if self.batimento_em is not None:
            tensao = meia_vida(self.tensao, t_ms - self.batimento_em, MEIA_VIDA_DA_TENSAO_MS)
        saida.append(self.nivel(tensao=tensao, dano_recente=self._dano(t_ms)))
        return saida

    def _dano(self, t_ms: float) -> float:
        return meia_vida(self.dano, t_ms - self.dano_em, MEIA_VIDA_DO_DANO_MS)
