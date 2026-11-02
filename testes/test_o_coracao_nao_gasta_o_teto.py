"""O coração do universal não gasta o teto do controle: o contínuo só se reescreve quando se sente.

A tensão que sobe devagar muda a força e o batimento do coração a cada tique; a saída só os
reescreve a cada degrau de :data:`motor.saida.DEGRAUS`, com intervalo mínimo por canal e controle e
sempre com vaga no teto para o evento, que sai no tique dele.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

from apoio import UM, EscritasDeMentira

import servidor
from motor import saida as modulo
from motor.arbitragem import Pedido, Vaga
from motor.laco import Motor
from motor.saida import Saida

TIQUE = 1000 / 60
ESTALO_MS = 30_000.0
Evento = tuple[str, str, "str | None", dict[str, Any]]


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


def _correr(porta: EscritasDeMentira, ate_ms: float, eventos: Sequence[tuple[float, Evento]],
            olhar: Callable[[float, dict[Vaga, Pedido]], None]) -> None:
    motor = Motor(servidor.carregar_o_universal())
    motor.controles([{"uniq": UM, "jogador": 1}])
    saida = Saida(porta.pedir)
    fila = sorted(eventos, key=lambda e: e[0])

    async def correr() -> None:
        k = 0
        while (t := k * TIQUE) <= ate_ms:
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            vencedores = motor.passo(t)
            await saida.aplicar(t, vencedores)
            olhar(t, vencedores)
            k += 1

    asyncio.run(correr())


def _a_cena_do_segundo_30() -> tuple[EscritasDeMentira, list[tuple[float, dict[Vaga, Pedido]]]]:
    linha = [(float(t), _microfone(0.01)) for t in range(0, 34_000, 500)]
    linha += [(float(t), _giro()) for t in range(0, 34_000, 400)]
    linha += [(ESTALO_MS, _estalo("esquerdo", 30.0))]
    vistos: list[tuple[float, dict[Vaga, Pedido]]] = []
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(porta, 33_000, linha, lambda t, v: vistos.append((t, dict(v))))
    return porta, vistos


def _no_maximo_por_segundo(instantes: list[float]) -> int:
    return max((sum(1 for o in instantes if t <= o < t + 1000) for t in instantes), default=0)


def test_o_coracao_com_a_tensao_subindo_devagar_escreve_no_maximo_4_por_segundo() -> None:
    porta, _ = _a_cena_do_segundo_30()
    coracao = [t for t, p in porta.de("haptica.tocar") if p["id"] == "coracao"]  # (noqa-acento)
    assert coracao and coracao[0] < 15_000
    assert _no_maximo_por_segundo(coracao) <= 4
    antes_do_estalo = [t for t, _, p in porta.escritas if p["uniq"] == UM and t < ESTALO_MS]
    assert _no_maximo_por_segundo(antes_do_estalo) <= 4


def test_o_estalo_e_o_susto_do_segundo_30_saem_no_tique_deles() -> None:
    porta, vistos = _a_cena_do_segundo_30()

    def tique(condicao: Callable[[dict[Vaga, Pedido]], bool]) -> float:
        return next(t for t, v in vistos if t >= ESTALO_MS and condicao(v))

    do_estalo = tique(lambda v: (UM, "motor", "esquerdo") in v)
    do_susto = tique(lambda v: any(p.efeito == "susto_no_tato" for p in v.values()))
    do_som = tique(lambda v: (UM, "som", "-") in v)
    motor = next(t for t, p in porta.de("vibracao.set") if t >= ESTALO_MS and p["forte"])
    susto = next(t for t, p in porta.de("haptica.tocar") if p["id"] == "susto")
    som = next(t for t, _ in porta.de("som.tocar"))
    assert motor - do_estalo <= TIQUE + 1e-6
    assert susto - do_susto <= TIQUE + 1e-6
    assert som - do_som <= TIQUE + 1e-6


def test_o_batimento_e_a_forca_que_o_controle_toca_seguem_a_tensao_dentro_do_degrau() -> None:
    porta = EscritasDeMentira(com_haptica=True)
    erros: list[tuple[float, float]] = []

    def olhar(t: float, vencedores: dict[Vaga, Pedido]) -> None:
        pedido = vencedores.get((UM, "haptica", "esquerdo"))
        tocados = [p for _, p in porta.de("haptica.tocar") if p["lado"] == "esquerdo"]
        if pedido is None or pedido.efeito != "coracao" or not tocados:  # (noqa-acento)
            return
        erros.append((abs(tocados[-1]["bpm"] - pedido.params["bpm"]),
                      abs(tocados[-1]["forca"] - pedido.params["forca"])))

    linha = [(float(t), _microfone(0.01)) for t in range(0, 29_000, 500)]
    linha += [(float(t), _giro()) for t in range(0, 29_000, 400)]
    _correr(porta, 29_000, linha, olhar)
    assert len(erros) > 600
    assert max(b for b, _ in erros) <= modulo.DEGRAUS["bpm"] + 0.5
    assert max(f for _, f in erros) <= modulo.DEGRAUS["forca"] + 0.001
    assert max(b for b, _ in erros) > 1


def _coracao(forca: float, bpm: float) -> dict[Vaga, Pedido]:
    params = {"inicio_ms": 0.0, "forca": forca, "padrao": "coracao", "bpm": bpm}  # (noqa-acento)
    return {(UM, "haptica", lado): Pedido(UM, "haptica", lado, "coracao", forca, 0, 0.0, 0,  # (noqa-acento)
                                          dict(params)) for lado in ("esquerdo", "direito")}


def _aplicar(saida: Saida, porta: EscritasDeMentira, t: float,
             vencedores: dict[Vaga, Pedido]) -> None:
    porta.agora = t
    asyncio.run(saida.aplicar(t, vencedores))


def test_a_tensao_que_corre_reescreve_o_coracao_no_maximo_uma_vez_por_intervalo() -> None:
    porta = EscritasDeMentira(com_haptica=True)
    saida = Saida(porta.pedir)
    for k in range(120):
        _aplicar(saida, porta, k * TIQUE, _coracao(min(1.0, 0.1 + 0.01 * k), 60 + k))
    escritas = [t for t, _ in porta.de("haptica.tocar")]
    assert _no_maximo_por_segundo(escritas) <= 2 * 1000 / modulo.INTERVALO_DO_DEGRAU_MS
    assert len(escritas) >= 6


def test_o_coracao_que_cai_a_zero_sai_no_tique_dele_mesmo_dentro_do_intervalo() -> None:
    porta = EscritasDeMentira(com_haptica=True)
    saida = Saida(porta.pedir)
    _aplicar(saida, porta, 0.0, _coracao(0.4, 90))
    _aplicar(saida, porta, 600.0, _coracao(0.5, 90))
    _aplicar(saida, porta, 600.0 + TIQUE, _coracao(0.0, 90))
    ultimas = [(t, p["forca"]) for t, p in porta.de("haptica.tocar")][-2:]
    assert ultimas == [(600.0 + TIQUE, 0.0), (600.0 + TIQUE, 0.0)]


def test_o_degrau_do_coracao_deixa_vaga_no_teto_para_o_evento_do_mesmo_tique() -> None:
    porta = EscritasDeMentira(com_haptica=True)
    saida = Saida(porta.pedir)
    _aplicar(saida, porta, 0.0, _coracao(0.4, 90))
    t = 600.0
    for k in range(modulo.TETO_POR_CONTROLE - 2 - 2):
        t = 600.0 + k * TIQUE
        luz = Pedido(UM, "luz", "-", f"luz{k}", 1.0, 0, t, 1,
                     {"inicio_ms": t, "rgb": [255, k, 0], "brilho": 1.0})
        _aplicar(saida, porta, t, {**_coracao(0.4, 90), (UM, "luz", "-"): luz})
    t += TIQUE
    golpe = Pedido(UM, "motor", "esquerdo", "golpe", 0.7, 0, t, 2, {"inicio_ms": t, "forca": 0.7})
    _aplicar(saida, porta, t, {**_coracao(0.6, 120), (UM, "motor", "esquerdo"): golpe})
    assert [p["forte"] for tt, p in porta.de("vibracao.set") if tt == t] == [round(0.7 * 255)]
    assert not [p for tt, p in porta.de("haptica.tocar") if tt == t]
