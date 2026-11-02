"""O coração pelo motor também deixa vaga para o evento: a batida conta no teto e se adia, o evento não.

Sem a háptica na porta, o coração se desenha no motor pelo envelope, e cada batida é um
``vibracao.set``. A batida só sai com :data:`motor.saida.VAGA_DO_EVENTO` escritas ainda livres no
teto, a mesma vaga do pedido vivo pela háptica; o estalo e o susto saem no tique deles.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

import pytest
from apoio import QUATRO_CONTROLES, UM, EscritasDeMentira

import servidor
from motor import saida as modulo
from motor.arbitragem import Pedido, Vaga
from motor.laco import Motor
from motor.saida import Saida

TIQUE = 1000 / 60
ESTALO_MS = 30_000.0
TETO_DA_BATIDA = modulo.TETO_POR_CONTROLE - modulo.VAGA_DO_EVENTO
Evento = tuple[str, str, "str | None", dict[str, Any]]


def _no_maximo_por_segundo(instantes: list[float]) -> int:
    return max((sum(1 for o in instantes if t <= o < t + 1000) for t in instantes), default=0)


def _microfone(nivel: float) -> Evento:
    return ("microfone.nivel", "microfone.nivel", UM,
            {"uniq": UM, "nivel": nivel, "mudo": False, "do_jogo": False, "t": 0.0})


def _giro() -> Evento:
    return ("movimento", "controle.movimento", UM, {
        "uniq": UM, "transporte": "bt", "giro": {"x": 0.0, "y": 0.0, "z": 3.0},
        "acel": {"x": 0.0, "y": 0.0, "z": 1.0}})


def _estalo(lado: str, t_s: float) -> Evento:
    return ("jogo.som", "jogo.som", None, {"t": t_s, "evento": "estalo", "lado": lado,
                                           "energia": 0.45, "canais": 2, "bandas": [0.0] * 24})


def _a_cena_do_segundo_30() -> tuple[EscritasDeMentira, Saida,
                                     list[tuple[float, dict[Vaga, Pedido]]]]:
    motor = Motor(servidor.carregar_o_universal())
    motor.controles([{"uniq": UM, "jogador": 1}])
    porta = EscritasDeMentira(com_som=True)
    saida = Saida(porta.pedir, None, motor.recusado, motor.pelo_motor)
    linha: list[tuple[float, Evento]] = [(float(t), _microfone(0.01)) for t in range(0, 34_000, 500)]
    linha += [(float(t), _giro()) for t in range(0, 34_000, 400)]
    linha += [(ESTALO_MS, _estalo("esquerdo", 30.0))]
    fila = sorted(linha, key=lambda e: e[0])
    vistos: list[tuple[float, dict[Vaga, Pedido]]] = []

    async def correr() -> None:
        k = 0
        while (t := k * TIQUE) <= 33_000:
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            vencedores = motor.passo(t)
            await saida.aplicar(t, vencedores)
            vistos.append((t, dict(vencedores)))
            k += 1

    asyncio.run(correr())
    return porta, saida, vistos


def test_o_coracao_pelo_motor_do_universal_nunca_passa_do_teto_menos_a_vaga() -> None:
    porta, saida, _ = _a_cena_do_segundo_30()
    assert saida.sem_haptica
    batidas = [t for t, _ in porta.de("vibracao.set") if t < ESTALO_MS]
    assert len(batidas) > 100
    assert _no_maximo_por_segundo(batidas) <= TETO_DA_BATIDA
    antes_do_estalo = [t for t, _, p in porta.escritas if p["uniq"] == UM and t < ESTALO_MS]
    assert _no_maximo_por_segundo(antes_do_estalo) <= TETO_DA_BATIDA


def test_o_estalo_e_o_susto_pelo_motor_saem_no_tique_deles() -> None:
    porta, _, vistos = _a_cena_do_segundo_30()

    def tique(condicao: Callable[[dict[Vaga, Pedido]], bool]) -> float:
        return next(t for t, v in vistos if t >= ESTALO_MS and condicao(v))

    do_estalo = tique(lambda v: (UM, "motor", "esquerdo") in v)
    do_susto = tique(lambda v: any(p.efeito == "susto_no_tato" for p in v.values()))
    do_som = tique(lambda v: (UM, "som", "-") in v)
    cheio = next(t for t, p in porta.de("vibracao.set") if t >= ESTALO_MS and p["forte"] == 255)
    som = next(t for t, _ in porta.de("som.tocar"))
    assert cheio - max(do_estalo, do_susto) <= TIQUE + 1e-6
    assert som - do_som <= TIQUE + 1e-6


def _coracao(uniq: str, bpm: float) -> dict[Vaga, Pedido]:
    params = {"inicio_ms": 0.0, "forca": 0.5, "padrao": "coracao", "bpm": bpm}  # (noqa-acento)
    return {(uniq, "haptica", lado): Pedido(uniq, "haptica", lado, "coracao", 0.5, 0, 0.0, 0,  # (noqa-acento)
                                            dict(params)) for lado in ("esquerdo", "direito")}


def _o_evento(uniq: str, t: float) -> dict[Vaga, Pedido]:
    susto = {"inicio_ms": t, "forca": 1.0, "padrao": "susto", "bpm": 72.0}  # (noqa-acento)
    return {
        (uniq, "haptica", "esquerdo"): Pedido(uniq, "haptica", "esquerdo", "susto_no_tato", 1.0,
                                              0, t, 7, dict(susto)),
        (uniq, "haptica", "direito"): Pedido(uniq, "haptica", "direito", "susto_no_tato", 1.0,
                                             0, t, 7, dict(susto)),
        (uniq, "motor", "esquerdo"): Pedido(uniq, "motor", "esquerdo", "estalo", 0.7, 0, t, 8,
                                            {"inicio_ms": t, "forca": 0.7}),
        (uniq, "luz", "-"): Pedido(uniq, "luz", "-", "clarao", 1.0, 0, t, 9,
                                   {"inicio_ms": t, "rgb": [255, 255, 255], "brilho": 1.0}),
    }


def _o_coracao_rapido_e_o_evento(controles: Sequence[str], bpm: float, evento_ms: float
                                 ) -> EscritasDeMentira:
    porta = EscritasDeMentira()
    saida = Saida(porta.pedir)
    alvo = controles[-1]

    async def correr() -> None:
        k = 0
        while (t := k * TIQUE) <= evento_ms + 400:
            vencedores: dict[Vaga, Pedido] = {}
            for uniq in controles:
                vencedores.update(_coracao(uniq, bpm))
            if t >= evento_ms:
                vencedores.update(_o_evento(alvo, evento_ms))
            porta.agora = t
            await saida.aplicar(t, vencedores)
            k += 1

    asyncio.run(correr())
    assert saida.sem_haptica
    return porta


@pytest.mark.parametrize("fase", range(0, 20, 3))
@pytest.mark.parametrize("bpm", [150.0, 180.0])
@pytest.mark.parametrize("quantos", [1, 4])
def test_o_coracao_rapido_pelo_motor_deixa_o_estalo_e_o_susto_sairem_no_tique_deles(
        quantos: int, bpm: float, fase: int) -> None:
    controles = [str(c["uniq"]) for c in QUATRO_CONTROLES[:quantos]]
    alvo = controles[-1]
    evento_ms = (180 + fase) * TIQUE
    porta = _o_coracao_rapido_e_o_evento(controles, bpm, evento_ms)
    no_tique = [(m, p) for t, m, p in porta.escritas if t == evento_ms and p["uniq"] == alvo]
    assert ("vibracao.set", {"uniq": alvo, "fraco": 255, "forte": 255}) in no_tique
    assert ("luz.set", {"uniq": alvo, "rgb": [255, 255, 255], "brilho": 1.0}) in no_tique
    for uniq in controles:
        batidas = [t for t, p in porta.de("vibracao.set") if p["uniq"] == uniq and t < evento_ms]
        assert len(batidas) > 20
        assert _no_maximo_por_segundo(batidas) <= TETO_DA_BATIDA
    janela = [t for t, _, p in porta.escritas if p["uniq"] == alvo and evento_ms - 1000 < t]
    assert _no_maximo_por_segundo(janela) <= modulo.TETO_POR_CONTROLE
    assert _no_maximo_por_segundo([t for t, _, _ in porta.escritas]) <= modulo.TETO_TOTAL


def test_o_coracao_que_para_solta_o_motor_no_tique_dele_mesmo_com_o_teto_cheio() -> None:
    porta = EscritasDeMentira()
    saida = Saida(porta.pedir)

    async def correr() -> float:
        k = 0
        while (t := k * TIQUE) <= 2000:
            porta.agora = t
            await saida.aplicar(t, _coracao(UM, 180.0))
            k += 1
        while porta.escritas[-1][2]["forte"] == 0:
            porta.agora = t = k * TIQUE
            await saida.aplicar(t, _coracao(UM, 180.0))
            k += 1
        porta.agora = t = k * TIQUE
        await saida.aplicar(t, {})
        return t

    fim = asyncio.run(correr())
    assert porta.escritas[-1] == (fim, "vibracao.set", {"uniq": UM, "fraco": 0, "forte": 0})
