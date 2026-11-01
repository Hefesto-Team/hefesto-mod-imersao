"""A escrita recusada não apaga a que já está no controle.

A porta recusa com ``-32011`` a escrita que o jogo vence no canal, e o que a extensão escreveu antes
continua no controle. A conta da saída devolve a chave ao valor de antes do pedido: quando a
receita solta o canal, ou a extensão sai, o zero do que ficou escrito sai. Vale para o motor, o
gatilho e a háptica, de P1 a P4; o ``uniq`` é o mesmo no cabo e no rádio.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from apoio import DOIS, QUATRO, TRES, UM, EscritasDeMentira, Recusa

from motor.arbitragem import Pedido, Vaga
from motor.saida import RENOVA_MS, Saida

Vencedores = dict[Vaga, Pedido]


class PortaQueRecusa(EscritasDeMentira):
    """A porta que recusa com ``-32011`` os params marcados, e aceita o resto."""

    def __init__(self) -> None:
        super().__init__(com_haptica=True)
        self.recusar: list[dict[str, Any]] = []
        self.recusas: list[tuple[float, str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if params in self.recusar:
            self.recusas.append((self.agora, metodo, dict(params)))
            raise Recusa("mais fraco que o pedido vivo no canal", -32011)
        return await super().pedir(metodo, params)


def _pedido(uniq: str, canal: str, lado: str, **params: Any) -> Vencedores:
    pedido = Pedido(uniq, canal, lado, "efeito", 1.0, 0, 0.0, 0, params)
    return {pedido.vaga: pedido}


def _gatilho(uniq: str, nome: str, valores: list[int]) -> Vencedores:
    return _pedido(uniq, "gatilho", "direito", trigger=(nome, valores))


def _motor(uniq: str, forca: float) -> Vencedores:
    return _pedido(uniq, "motor", "esquerdo", forca=forca)


def _haptica(uniq: str, forca: float) -> Vencedores:
    return _pedido(uniq, "haptica", "esquerdo", padrao="estalo", forca=forca, bpm=72.0,
                   inicio_ms=0.0)


def _escrita_do_gatilho(uniq: str, nome: str, valores: list[int]) -> dict[str, Any]:
    return {"uniq": uniq, "lado": "direito", "modo": nome, "params": valores}


def _escrita_do_motor(uniq: str, forca: float) -> dict[str, Any]:
    return {"uniq": uniq, "fraco": 0, "forte": round(forca * 255)}


def _escrita_da_haptica(uniq: str, forca: float) -> dict[str, Any]:
    return {"uniq": uniq, "id": "estalo", "forca": forca, "bpm": 72, "lado": "esquerdo",
            "ate_ms": 3000}


CANAIS = {
    "gatilho": ("gatilho.set",
                lambda u: _gatilho(u, "Rigid", [0, 120]), lambda u: _gatilho(u, "Rigid", [0, 255]),
                lambda u: _escrita_do_gatilho(u, "Rigid", [0, 255]),
                lambda u: {"uniq": u, "lado": "direito", "modo": "Off", "params": []}),
    "motor": ("vibracao.set",
              lambda u: _motor(u, 0.4), lambda u: _motor(u, 0.8),
              lambda u: _escrita_do_motor(u, 0.8),
              lambda u: {"uniq": u, "fraco": 0, "forte": 0}),
    "haptica": ("haptica.tocar",
                lambda u: _haptica(u, 0.4), lambda u: _haptica(u, 0.8),
                lambda u: _escrita_da_haptica(u, 0.8),
                lambda u: {**_escrita_da_haptica(u, 0.4), "forca": 0.0, "ate_ms": 0}),
}


def _correr(saida: Saida, porta: PortaQueRecusa,
            linha: list[tuple[float, Vencedores | None]]) -> None:
    async def correr() -> None:
        for t_ms, vencedores in linha:
            porta.agora = t_ms
            if vencedores is None:
                await saida.soltar_tudo(t_ms)
            else:
                await saida.aplicar(t_ms, vencedores)

    asyncio.run(correr())


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("canal", sorted(CANAIS))
def test_a_receita_que_solta_o_canal_depois_da_recusa_zera_o_que_ficou_escrito(
        canal: str, uniq: str) -> None:
    metodo, aceito, recusado, escrita_recusada, zero = CANAIS[canal]
    porta = PortaQueRecusa()
    porta.recusar.append(escrita_recusada(uniq))
    saida = Saida(porta.pedir)
    _correr(saida, porta, [(0.0, aceito(uniq)), (100.0, recusado(uniq)), (200.0, {})])
    assert [(t, m) for t, m, _ in porta.recusas] == [(100.0, metodo)]
    escritas = porta.de(metodo)
    assert [t for t, _ in escritas] == [0.0, 200.0]
    assert escritas[-1][1] == zero(uniq)
    assert [params for _, params in saida.escrito.values()] == [zero(uniq)]


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("canal", sorted(CANAIS))
def test_a_extensao_que_sai_depois_da_recusa_zera_o_que_tinha_escrito_antes(
        canal: str, uniq: str) -> None:
    metodo, aceito, recusado, escrita_recusada, zero = CANAIS[canal]
    porta = PortaQueRecusa()
    porta.recusar.append(escrita_recusada(uniq))
    saida = Saida(porta.pedir)
    _correr(saida, porta, [(0.0, aceito(uniq)), (100.0, recusado(uniq)),
                           (116.0, recusado(uniq)), (300.0, None)])
    assert [t for t, _, _ in porta.recusas] == [100.0]
    escritas = porta.de(metodo)
    assert [t for t, _ in escritas] == [0.0, 300.0]
    assert escritas[-1][1] == zero(uniq)


def test_a_conta_diz_o_que_ficou_no_controle_e_a_volta_ao_valor_aceito_nao_se_repete() -> None:
    porta = PortaQueRecusa()
    porta.recusar.append(_escrita_do_gatilho(UM, "Rigid", [0, 255]))
    saida = Saida(porta.pedir)
    _correr(saida, porta, [(0.0, _gatilho(UM, "Rigid", [0, 120])),
                           (100.0, _gatilho(UM, "Rigid", [0, 255])),
                           (200.0, _gatilho(UM, "Rigid", [0, 120]))])
    chave = (UM, "gatilho", "direito")
    assert saida.escrito[chave] == (0.0, _escrita_do_gatilho(UM, "Rigid", [0, 120]))
    assert [t for t, _ in porta.de("gatilho.set")] == [0.0]


def test_a_recusa_sem_nada_escrito_antes_deixa_a_conta_vazia_e_nao_manda_zero() -> None:
    porta = PortaQueRecusa()
    porta.recusar.append(_escrita_do_motor(UM, 0.8))
    saida = Saida(porta.pedir)
    _correr(saida, porta, [(0.0, _motor(UM, 0.8)), (100.0, {}), (200.0, None)])
    assert saida.escrito == {}
    assert porta.de("vibracao.set") == []


def test_a_recusa_devolve_o_instante_da_escrita_aceita_e_a_renovacao_conta_dele() -> None:
    porta = PortaQueRecusa()
    porta.recusar.append(_escrita_do_motor(UM, 0.8))
    saida = Saida(porta.pedir)
    _correr(saida, porta, [(0.0, _motor(UM, 0.4)), (1000.0, _motor(UM, 0.8)),
                           (RENOVA_MS, _motor(UM, 0.4))])
    assert [t for t, _ in porta.de("vibracao.set")] == [0.0, RENOVA_MS]


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("canal", sorted(CANAIS))
def test_o_zero_recusado_nao_se_repete_com_o_canal_solto_e_a_conta_segue_com_o_aceito(
        canal: str, uniq: str) -> None:
    metodo, aceito, _, _, zero = CANAIS[canal]
    porta = PortaQueRecusa()
    porta.recusar.append(zero(uniq))
    saida = Saida(porta.pedir)
    _correr(saida, porta, [(0.0, aceito(uniq)), (100.0, {}), (116.0, {}), (1000.0, {})])
    assert [(t, m) for t, m, _ in porta.recusas] == [(100.0, metodo)]
    assert [t for t, _ in porta.de(metodo)] == [0.0]
    assert [t for t, _ in saida.escrito.values()] == [0.0]


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("canal", sorted(CANAIS))
def test_a_extensao_que_sai_tenta_de_novo_o_zero_que_a_porta_recusou(
        canal: str, uniq: str) -> None:
    metodo, aceito, _, _, zero = CANAIS[canal]
    porta = PortaQueRecusa()
    porta.recusar.append(zero(uniq))
    saida = Saida(porta.pedir)

    async def correr() -> None:
        porta.agora = 0.0
        await saida.aplicar(0.0, aceito(uniq))
        porta.agora = 100.0
        await saida.aplicar(100.0, {})
        porta.recusar.clear()
        porta.agora = 300.0
        await saida.soltar_tudo(300.0)

    asyncio.run(correr())
    assert [(t, m) for t, m, _ in porta.recusas] == [(100.0, metodo)]
    escritas = porta.de(metodo)
    assert [t for t, _ in escritas] == [0.0, 300.0]
    assert escritas[-1][1] == zero(uniq)
