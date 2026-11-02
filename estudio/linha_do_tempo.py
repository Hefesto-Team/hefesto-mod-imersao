"""A linha do tempo: «Gravar» guarda cinco minutos de sinais, «Tocar» os repete com a receita de agora.

Só entram sinais derivados, nunca áudio nem imagem: as bandas e o lado do estalo (``jogo.som``),
a vibração que o jogo pede (``jogo.vibracao``), os números da tela (``jogo.tela``) e o estado da
memória (``jogo.memoria``). O ``microfone.nivel`` nunca se grava: no «Tocar», o sentido do
microfone lê o microfone ao vivo. Quem joga ajusta um bloco e toca de novo sem abrir o jogo.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from motor.laco import HZ, Motor
from receita.formato import Receita

DURACAO_MS = 5 * 60 * 1000.0
TOPICOS_GRAVADOS = ("jogo.som", "jogo.vibracao", "jogo.tela", "jogo.memoria")
CAMPOS_DO_SOM = ("t", "evento", "lado", "energia", "canais", "bandas")
PASTA_DAS_LINHAS = "linhas"
TIPOS_DO_GRAVADOR = ("gravar", "parar", "tocar")


@dataclass(frozen=True)
class Marco:
    """Um sinal gravado, no instante contado do começo da gravação."""

    t_ms: float
    topico: str
    nome: str
    uniq: str | None
    dados: dict[str, Any]

    def para_json(self) -> list[Any]:
        return [round(self.t_ms, 1), self.topico, self.nome, self.uniq, self.dados]

    @classmethod
    def de_json(cls, item: Any) -> Marco:
        t_ms, topico, nome, uniq, dados = item
        if (not isinstance(t_ms, (int, float)) or topico not in TOPICOS_GRAVADOS
                or not isinstance(nome, str) or not isinstance(dados, dict)):
            raise ValueError("marco fora do formato")
        return cls(float(t_ms), topico, nome, uniq if isinstance(uniq, str) else None, dados)


@dataclass
class LinhaDoTempo:
    """Os marcos de uma gravação, em ordem, até :data:`DURACAO_MS`."""

    marcos: list[Marco] = field(default_factory=list)

    @property
    def duracao_ms(self) -> float:
        return self.marcos[-1].t_ms if self.marcos else 0.0

    def para_json(self) -> bytes:
        return json.dumps({"formato": 1, "marcos": [m.para_json() for m in self.marcos]},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    @classmethod
    def de_json(cls, bruto: bytes) -> LinhaDoTempo:
        dados = json.loads(bruto)
        if not isinstance(dados, dict) or dados.get("formato") != 1:
            raise ValueError("linha do tempo fora do formato")
        marcos = [Marco.de_json(m) for m in dados.get("marcos", [])]
        return cls(sorted(marcos, key=lambda m: m.t_ms))


def _so_o_sinal(topico: str, dados: dict[str, Any]) -> dict[str, Any]:
    if topico == "jogo.som":
        return {k: dados[k] for k in CAMPOS_DO_SOM if k in dados}
    return dict(dados)


class Gravador:
    """Grava os tópicos de :data:`TOPICOS_GRAVADOS` enquanto ligado, por até cinco minutos."""

    def __init__(self) -> None:
        self.inicio_ms: float | None = None
        self.linha = LinhaDoTempo()

    @property
    def gravando(self) -> bool:
        return self.inicio_ms is not None

    def gravar(self, t_ms: float) -> None:
        self.inicio_ms, self.linha = t_ms, LinhaDoTempo()

    def parar(self) -> LinhaDoTempo:
        self.inicio_ms = None
        return self.linha

    def ouvir(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
              t_ms: float) -> None:
        if self.inicio_ms is None or topico not in TOPICOS_GRAVADOS:
            return
        passou = t_ms - self.inicio_ms
        if passou > DURACAO_MS:
            self.parar()
            return
        self.linha.marcos.append(Marco(passou, topico, nome, uniq, _so_o_sinal(topico, dados)))


def efeitos_da_linha(linha: LinhaDoTempo, receita: Receita, controles: list[dict[str, Any]],
                     opcoes: dict[str, Any] | None = None,
                     ao_vivo: Iterable[Marco] = ()) -> list[tuple[float, str, str, str, str]]:
    """O que a receita faria com a linha, tique a tique: ``(t, controle, canal, lado, efeito)``.

    Cada vencedor novo de uma vaga entra uma vez, no tique em que começa. ``ao_vivo`` soma os
    sinais que não se gravam (o microfone), como no «Tocar».
    """
    motor = Motor(receita, opcoes)
    motor.controles(controles)
    fila = sorted([*linha.marcos, *ao_vivo], key=lambda m: m.t_ms)
    passo = 1000.0 / HZ
    saida: list[tuple[float, str, str, str, str]] = []
    vigentes: dict[tuple[str, str, str], tuple[str, float]] = {}
    t, i = 0.0, 0
    fim = (fila[-1].t_ms if fila else 0.0) + 1000.0
    while t <= fim:
        while i < len(fila) and fila[i].t_ms <= t:
            marco = fila[i]
            motor.evento(marco.topico, marco.nome, marco.uniq, marco.dados)
            i += 1
        vencedores = motor.passo(t)
        agora = {vaga: (p.efeito, p.inicio_ms) for vaga, p in vencedores.items() if p.forca > 0}
        for vaga, (efeito, inicio) in agora.items():
            if vigentes.get(vaga) != (efeito, inicio):
                saida.append((round(t, 1), *vaga, efeito))
        vigentes = agora
        t += passo
    return saida


async def tocar(linha: LinhaDoTempo, evento: Callable[[str, str, str | None, dict[str, Any]], None],
                parar: asyncio.Event,
                dormir: Callable[[float], Awaitable[Any]] = asyncio.sleep) -> None:
    """Repete a linha no motor vivo, no tempo dela; o laço da extensão escreve no controle."""
    feito = 0.0
    for marco in linha.marcos:
        if parar.is_set():
            return
        if marco.t_ms > feito:
            await dormir((marco.t_ms - feito) / 1000.0)
            feito = marco.t_ms
        evento(marco.topico, marco.nome, marco.uniq, marco.dados)


def gravar_no_disco(pasta: Path, chave: str, linha: LinhaDoTempo) -> Path:
    """A linha em ``<pasta>/linhas/<chave>.json``, trocada de uma vez."""
    destino = pasta / PASTA_DAS_LINHAS
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{chave}.json"
    temporario = arquivo.with_suffix(".json.novo")
    temporario.write_bytes(linha.para_json())
    os.replace(temporario, arquivo)
    return arquivo


def ler_do_disco(pasta: Path, chave: str) -> LinhaDoTempo | None:
    with contextlib.suppress(OSError, ValueError, TypeError):
        return LinhaDoTempo.de_json((pasta / PASTA_DAS_LINHAS / f"{chave}.json").read_bytes())
    return None
