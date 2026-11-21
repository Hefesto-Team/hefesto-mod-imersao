"""A escrita recusada não apaga a que já está no controle.

A porta recusa com ``-32011`` a escrita que o jogo vence no canal, e o que a extensão escreveu antes
continua no controle. A conta da saída devolve a chave ao valor de antes do pedido: quando a
receita solta o canal, ou a extensão sai, o zero do que ficou escrito sai. Vale para o motor, o
gatilho e a háptica, de P1 a P4; o ``uniq`` é o mesmo no cabo e no rádio.

O teto da porta (``-32014``) não deixa a escrita registrada: o impacto, o susto, a luz e as luzes de
jogador saem no tique em que a conta da extensão diz que cabe, e o motivo é «teto». A recusa sem
tratamento (sem permissão, sem ponte) se tenta de novo só no prazo da renovação, com uma linha no
diário por efeito e por motivo. Cada controle tem a sua conta, no cabo e no rádio.
"""
from __future__ import annotations

import asyncio
import random
from typing import Any

import pytest
from apoio import DOIS, QUATRO, TRES, UM, EscritasDeMentira, Recusa

from motor.arbitragem import Pedido, Vaga
from motor.saida import RENOVA_MS, TETO_POR_CONTROLE, Saida

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


def _pedido(uniq: str, canal: str, lado: str, efeito: str = "efeito", **params: Any) -> Vencedores:
    pedido = Pedido(uniq, canal, lado, efeito, 1.0, 0, 0.0, 0, params)
    return {pedido.vaga: pedido}


def _gatilho(uniq: str, nome: str, valores: list[int]) -> Vencedores:
    return _pedido(uniq, "gatilho", "direito", trigger=(nome, valores))


def _motor(uniq: str, forca: float, efeito: str = "efeito") -> Vencedores:
    return _pedido(uniq, "motor", "esquerdo", efeito, forca=forca)


def _haptica(uniq: str, forca: float, efeito: str = "efeito") -> Vencedores:
    return _pedido(uniq, "haptica", "esquerdo", efeito, padrao="estalo", forca=forca, bpm=72.0,
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
              lambda u: _motor(u, 0.4), lambda u: _motor(u, 0.8, "mais_forte"),
              lambda u: _escrita_do_motor(u, 0.8),
              lambda u: {"uniq": u, "fraco": 0, "forte": 0}),
    "haptica": ("haptica.tocar",
                lambda u: _haptica(u, 0.4), lambda u: _haptica(u, 0.8, "mais_forte"),
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


TIQUE_MS = 1000.0 / 60
SEM_PERMISSAO = -32010
TETO = -32014


class PortaQueRecusaPorCodigo(EscritasDeMentira):
    """A porta que recusa por controle com o código dado, até ``ate`` (ms); guarda cada tentativa."""

    def __init__(self) -> None:
        super().__init__(com_haptica=True, com_som=True)
        self.codigos: dict[str, int] = {}
        self.ate: dict[str, float] = {}
        self.tentativas: list[tuple[float, str, str]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        uniq = params.get("uniq")
        if metodo != "haptica.registrar":
            self.tentativas.append((self.agora, metodo, str(uniq)))
        if uniq in self.codigos and self.agora < self.ate.get(str(uniq), float("inf")):
            raise Recusa("recusado pela porta", self.codigos[str(uniq)])
        return await super().pedir(metodo, params)

    def de_um(self, metodo: str, uniq: str) -> list[float]:
        return [t for t, m, u in self.tentativas if m == metodo and u == uniq]


def _impacto(uniq: str) -> Vencedores:
    return _pedido(uniq, "gatilho", "direito", "impacto", trigger=("Rigid", [0, 255]))


def _susto(uniq: str) -> Vencedores:
    return _pedido(uniq, "som", "-", "susto", som="susto", volume=0.8, inicio_ms=0.0)


def _luz(uniq: str) -> Vencedores:
    return _pedido(uniq, "luz", "-", "vermelho", rgb=[255, 0, 0], brilho=1.0)


def _luzes(uniq: str) -> Vencedores:
    return _pedido(uniq, "leds", "-", "luzes", mascara=3, ate_ms=600, inicio_ms=0.0)


def _forte(uniq: str) -> Vencedores:
    return _motor(uniq, 0.8)


def _batida(uniq: str) -> Vencedores:
    return _haptica(uniq, 0.8)


PEDIDOS = {
    "impacto": ("gatilho.set", _impacto), "susto": ("som.tocar", _susto),
    "luz": ("luz.set", _luz), "luzes": ("leds.set", _luzes),
    "motor": ("vibracao.set", _forte), "haptica": ("haptica.tocar", _batida),
}
DE_UMA_VEZ = ("impacto", "susto", "luz", "luzes")


def _tiques(saida: Saida, porta: PortaQueRecusaPorCodigo, pedidos: Any, ms: float) -> None:
    async def correr() -> None:
        for i in range(round(ms / TIQUE_MS)):
            t_ms = i * TIQUE_MS
            porta.agora = t_ms
            await saida.aplicar(t_ms, pedidos(t_ms))

    asyncio.run(correr())


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("nome", DE_UMA_VEZ)
def test_o_teto_cheio_no_primeiro_tique_nao_perde_o_efeito_de_uma_vez(
        nome: str, uniq: str) -> None:
    metodo, pedido = PEDIDOS[nome]
    porta = PortaQueRecusaPorCodigo()
    porta.codigos[uniq], porta.ate[uniq] = TETO, 99.0
    saida = Saida(porta.pedir)
    _tiques(saida, porta, lambda _t: pedido(uniq), 1000.0)
    assert [t for t, _ in porta.de(metodo)] == [100.0]
    assert porta.de_um(metodo, uniq) == [i * TIQUE_MS for i in range(7)]
    assert saida.tirar_as_recusas() == []
    assert saida.tirar_os_desfechos()[2] != []


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("nome", DE_UMA_VEZ)
def test_o_teto_que_nao_abre_gasta_so_a_conta_da_extensao_e_o_motivo_e_teto(
        nome: str, uniq: str) -> None:
    metodo, pedido = PEDIDOS[nome]
    porta = PortaQueRecusaPorCodigo()
    porta.codigos[uniq] = TETO
    diario: list[str] = []
    saida = Saida(porta.pedir, diario.append)
    _tiques(saida, porta, lambda _t: pedido(uniq), 1000.0)
    assert porta.de(metodo) == []
    assert len(porta.de_um(metodo, uniq)) == TETO_POR_CONTROLE
    assert saida.escrito == {}
    assert saida.tirar_as_recusas() == []
    asyncio.run(saida.aplicar(2000.0, {}))
    [(dono, _canal, motivo)] = saida.tirar_as_recusas()
    assert (dono, motivo) == (uniq, "teto")
    assert diario == []


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
@pytest.mark.parametrize("nome", sorted(PEDIDOS))
def test_a_recusa_sem_tratamento_se_tenta_so_no_prazo_da_renovacao_e_o_diario_diz_uma_vez(
        nome: str, uniq: str) -> None:
    metodo, pedido = PEDIDOS[nome]
    porta = PortaQueRecusaPorCodigo()
    porta.codigos[uniq] = SEM_PERMISSAO
    diario: list[str] = []
    saida = Saida(porta.pedir, diario.append)
    _tiques(saida, porta, lambda _t: pedido(uniq), 6000.0)
    assert porta.de_um(metodo, uniq) == [0.0, RENOVA_MS, 2 * RENOVA_MS]
    assert [linha for linha in diario if "recusado" in linha] == [
        f"{metodo} recusado: recusado pela porta"]


def test_a_recusa_aceita_na_renovacao_para_de_se_tentar_e_o_susto_conta_como_tocado() -> None:
    porta = PortaQueRecusaPorCodigo()
    porta.codigos[UM], porta.ate[UM] = SEM_PERMISSAO, RENOVA_MS
    saida = Saida(porta.pedir)
    _tiques(saida, porta, lambda _t: _susto(UM), 6000.0)
    assert [t for t, _ in porta.de("som.tocar")] == [RENOVA_MS]
    assert porta.de_um("som.tocar", UM) == [0.0, RENOVA_MS]


def _a_mesa(ordem: int, sai_na_troca: bool) -> tuple[Saida, PortaQueRecusaPorCodigo, list[str]]:
    """Quatro controles no rádio (UM e DOIS no mesmo adaptador), o TRES passa para o cabo de 330 ms a
    660 ms (na troca que se vê como saída e volta, ele some da lista) e volta ao rádio; cada um pede o
    impacto, a luz e o susto. O UM e o QUATRO acham o teto cheio nos primeiros tiques, o DOIS não tem a
    permissão, o TRES escreve sem recusa."""
    porta = PortaQueRecusaPorCodigo()
    porta.codigos[UM], porta.ate[UM] = TETO, 40.0
    porta.codigos[QUATRO], porta.ate[QUATRO] = TETO, 20.0
    porta.codigos[DOIS] = SEM_PERMISSAO
    diario: list[str] = []
    saida = Saida(porta.pedir, diario.append)

    def pedidos(t_ms: float) -> Vencedores:
        vencedores: Vencedores = {}
        uniqs = [UM, DOIS, TRES, QUATRO]
        random.Random(ordem).shuffle(uniqs)
        for uniq in uniqs:
            if sai_na_troca and uniq == TRES and 330.0 <= t_ms < 660.0:
                continue
            for nome in ("impacto", "luz", "susto"):
                vencedores.update(PEDIDOS[nome][1](uniq))
        return vencedores

    _tiques(saida, porta, pedidos, 1000.0)
    return saida, porta, diario


def _do(porta: PortaQueRecusaPorCodigo, uniq: str) -> list[tuple[float, str]]:
    return [(t, m) for t, m, p in porta.escritas if p["uniq"] == uniq]


@pytest.mark.parametrize("ordem", [0, 1, 2])
def test_o_teto_e_a_recusa_de_cada_controle_atravessam_a_troca_de_transporte(ordem: int) -> None:
    fica, porta_fica, diario_fica = _a_mesa(ordem, sai_na_troca=False)
    some, porta_some, _ = _a_mesa(ordem, sai_na_troca=True)
    metodos = ("gatilho.set", "luz.set", "som.tocar")
    assert sorted(_do(porta_fica, UM)) == sorted((3 * TIQUE_MS, m) for m in metodos)
    assert sorted(_do(porta_fica, QUATRO)) == sorted((2 * TIQUE_MS, m) for m in metodos)
    assert sorted(_do(porta_fica, TRES)) == sorted((0.0, m) for m in metodos)
    assert _do(porta_fica, DOIS) == []
    assert [porta_fica.de_um(m, DOIS) for m in metodos] == [[0.0]] * 3
    assert sorted(linha for linha in diario_fica if "recusado" in linha) == sorted(
        f"{m} recusado: recusado pela porta" for m in metodos)
    for uniq in (UM, DOIS, QUATRO):
        assert _do(porta_some, uniq) == _do(porta_fica, uniq)
    do_tres = _do(porta_some, TRES)
    assert [m for _, m in do_tres].count("gatilho.set") == 3
    assert [m for _, m in do_tres].count("luz.set") == 2
    assert [m for _, m in do_tres].count("som.tocar") == 2
    assert fica._no_teto == set() == some._no_teto
    assert {c[0] for c in fica._falhou} == {DOIS} == {c[0] for c in some._falhou}
    asyncio.run(some.aplicar(2000.0, {k: v for k, v in _mesa_sem(TRES).items()}))
    assert all(c[0] != TRES for c in some._falhou | some._no_teto)
    assert all(d[0][0] != TRES for d in some._ditas)


def _mesa_sem(uniq: str) -> Vencedores:
    vencedores: Vencedores = {}
    for outro in (UM, DOIS, QUATRO):
        for nome in ("impacto", "luz", "susto"):
            vencedores.update(PEDIDOS[nome][1](outro))
    return vencedores


@pytest.mark.parametrize("uniq", [UM, DOIS, TRES, QUATRO])
def test_o_zero_que_o_teto_recusa_volta_so_na_conta_da_extensao_e_sai_quando_a_porta_abre(
        uniq: str) -> None:
    class PortaQueSegura(PortaQueRecusaPorCodigo):
        aberta = False

        async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
            if metodo == "vibracao.set" and not params["forte"] and not self.aberta:
                self.tentativas.append((self.agora, metodo, uniq))
                raise Recusa("teto", TETO)
            return await super().pedir(metodo, params)

    porta = PortaQueSegura()
    saida = Saida(porta.pedir)

    async def correr() -> None:
        await saida.aplicar(0.0, _motor(uniq, 0.8))
        for i in range(1, 60):
            porta.agora = i * TIQUE_MS
            await saida.aplicar(porta.agora, {})
        porta.aberta = True
        porta.agora = 1100.0
        await saida.aplicar(1100.0, {})

    asyncio.run(correr())
    zeros = [t for t, m, _ in porta.tentativas if m == "vibracao.set"]
    assert len(zeros) <= TETO_POR_CONTROLE + 1
    assert [t for t, p in porta.de("vibracao.set") if not p["forte"]] == [1100.0]
