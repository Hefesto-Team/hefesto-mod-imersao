"""O R2 do Minecraft Dungeons II tem a resistência de arco ao puxar enquanto a receita do jogo vale.

O efeito vale enquanto a regra vale, em cada controle da mesa de P1 a P4, no cabo e no rádio; o
impacto do golpe toca por cima e o arco volta. A saída renova o gatilho que não tem prazo, para a
porta não o soltar, e o devolve ao perfil quando ele acaba. O «Solto» não pede nada.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from itertools import pairwise
from typing import Any

import pytest
from apoio import DOIS, QUATRO, QUATRO_CONTROLES, TRES, UM, EscritasDeMentira, Recusa
from test_a_receita_minecraft_dungeons_ii import LINHA_DO_GATILHO, _golpe_no_r2, _receita
from test_o_universal import TIQUE, Evento, entradas

import servidor
from motor import efeitos as catalogo
from motor.laco import Motor
from motor.saida import ATE_MS_DO_GATILHO_CONTINUO, RENOVA_MS, Saida

UNIQS = (UM, DOIS, TRES, QUATRO)
ARCO = ("Bow", [1, 7, 4, 4])
EM_CENA: Evento = ("perfil.jogo", "perfil.trocou", None, {
    "perfil": "Jogo", "jogo": "steam_app_1912410", "em_cena": True, "estilo": None,
    "controles": [], "t": 1.0})
SEM_JOGO: Evento = ("perfil.jogo", "perfil.trocou", None, {
    "perfil": "Padrão", "jogo": None, "em_cena": False, "estilo": None, "controles": [],
    "t": 2.0})
Acao = Callable[[Motor], None]


def _motor(opcoes: dict[str, Any] | None = None,
           controles: Sequence[dict[str, Any]] = QUATRO_CONTROLES) -> Motor:
    motor = Motor(_receita(), opcoes)
    motor.controles(list(controles))
    return motor


def _correr(motor: Motor, porta: EscritasDeMentira, ate_ms: float,
            eventos: Sequence[tuple[float, Evento]] = (),
            acoes: Sequence[tuple[float, Acao]] = ()) -> Saida:
    fila = sorted(eventos, key=lambda e: e[0])
    agenda = sorted(acoes, key=lambda a: a[0])
    saida = Saida(porta.pedir)

    async def correr() -> None:
        k = 0
        while (t := k * TIQUE) <= ate_ms:
            while agenda and agenda[0][0] <= t + 1e-6:
                agenda.pop(0)[1](motor)
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            await saida.aplicar(t, motor.passo(t))
            k += 1

    asyncio.run(correr())
    return saida


def _gatilhos(porta: EscritasDeMentira, uniq: str = UM) -> list[tuple[int, str, str, Any, Any]]:
    return [(round(t), p["lado"], p["modo"], p["params"], p.get("ate_ms"))
            for t, p in porta.de("gatilho.set") if p["uniq"] == uniq]


def _viradas(escritas: list[tuple[int, str, str, Any, Any]]) -> list[tuple[str, int]]:
    """O primeiro instante de cada virada de modo: a renovação do mesmo modo não conta."""
    viradas: list[tuple[str, int]] = []
    for t, _, modo, _, _ in escritas:
        if not viradas or viradas[-1][0] != modo:
            viradas.append((modo, t))
    return viradas


@pytest.mark.parametrize("uniq", UNIQS)
def test_com_o_jogo_aberto_o_r2_de_cada_controle_nasce_em_arco_e_o_l2_fica_solto(uniq: str) -> None:
    porta = EscritasDeMentira()
    _correr(_motor(), porta, 500, [(0, EM_CENA)])
    assert _gatilhos(porta, uniq) == [(0, "direito", *ARCO, ATE_MS_DO_GATILHO_CONTINUO)]


def test_o_r2_em_arco_vale_para_a_mesa_inteira_sem_escrever_no_l2() -> None:
    porta = EscritasDeMentira()
    _correr(_motor(), porta, 500, [(0, EM_CENA)])
    assert {p["uniq"] for _, p in porta.de("gatilho.set")} == set(UNIQS)
    assert {p["lado"] for _, p in porta.de("gatilho.set")} == {"direito"}


def test_o_gatilho_sem_prazo_se_renova_a_cada_2500_ms_para_a_porta_nao_o_soltar() -> None:
    porta = EscritasDeMentira()
    _correr(_motor(), porta, 11_000, [(0, EM_CENA)])
    escritas = _gatilhos(porta)
    instantes = [t for t, *_ in escritas]
    assert len(instantes) == 5 and instantes[0] == 0
    assert all(2500 <= b - a < 2520 for a, b in pairwise(instantes))
    assert {(modo, tuple(params), ate) for _, _, modo, params, ate in escritas} == {
        (ARCO[0], tuple(ARCO[1]), ATE_MS_DO_GATILHO_CONTINUO)}
    assert RENOVA_MS == 2500


@pytest.mark.parametrize("transporte", ["usb", "bt"])
@pytest.mark.parametrize("escolha", ["Vibração", "Arco"])
def test_o_impacto_do_golpe_toca_por_cima_e_ao_acabar_o_arco_volta(
        transporte: str, escolha: str) -> None:
    porta = EscritasDeMentira()
    golpe = [(t + 1000, e) for t, e in _golpe_no_r2(0)]
    golpe[0] = (1000, entradas(UM, 200, transporte=transporte))
    _correr(_motor({"tipo_do_r2": escolha}, [{"uniq": UM, "jogador": 1}]), porta, 3000,
            [(0, EM_CENA), *golpe])
    escritas = _gatilhos(porta)
    impacto = ("Bow", [1, 7, 6, 6]) if escolha == "Arco" else ("Vibration", [2, 6, 40])
    assert [(modo, params) for _, _, modo, params, _ in escritas] == [ARCO, impacto, ARCO]
    assert escritas[1][4] == 150
    assert 1000 < escritas[1][0] < 1200
    assert escritas[2][0] - escritas[1][0] in range(150, 170)
    assert escritas[2][4] == ATE_MS_DO_GATILHO_CONTINUO


def test_o_impacto_e_sempre_mais_forte_que_o_arco_em_qualquer_forca() -> None:
    receita = _receita()
    efeitos = receita.secao("efeitos")
    for forca in (1.0, 0.75, 0.5, 0.25, 0.1):
        arco = catalogo.forca_do_gatilho(catalogo.gatilho_na_escala(efeitos["r2_ao_puxar"], forca))
        impacto = catalogo.forca_do_gatilho(
            catalogo.gatilho_na_escala(efeitos["impacto_no_r2"], forca))
        assert arco <= impacto


def test_o_solto_nao_manda_nada_e_o_impacto_toca_sozinho() -> None:
    porta = EscritasDeMentira()
    _correr(_motor({"tipo_do_r2_ao_puxar": "Solto"}), porta, 5000, [(0, EM_CENA)])
    assert not porta.de("gatilho.set")
    porta = EscritasDeMentira()
    _correr(_motor({"tipo_do_r2_ao_puxar": "Solto"}, [{"uniq": UM, "jogador": 1}]), porta, 3000,
            [(0, EM_CENA), *((t + 1000, e) for t, e in _golpe_no_r2(0))])
    assert [(modo, ate) for _, _, modo, _, ate in _gatilhos(porta)] == [("Vibration", 150),
                                                                         ("Off", None)]


@pytest.mark.parametrize(("escolha", "modo"), [("Resistência", "Resistance"), ("Disparo", "Weapon"),
                                                ("Galope", "Galloping"), ("Vibração", "Vibration")])
def test_o_tipo_escolhido_para_o_r2_ao_puxar_chega_ao_gatilho_set(escolha: str, modo: str) -> None:
    porta = EscritasDeMentira()
    _correr(_motor({"tipo_do_r2_ao_puxar": escolha}, [{"uniq": UM, "jogador": 1}]), porta, 500,
            [(0, EM_CENA)])
    assert [(m, ate) for _, _, m, _, ate in _gatilhos(porta)] == [
        (modo, ATE_MS_DO_GATILHO_CONTINUO)]


def test_trocar_o_tipo_para_solto_com_o_jogo_aberto_devolve_o_gatilho_ao_perfil() -> None:
    porta = EscritasDeMentira()
    _correr(_motor(controles=[{"uniq": UM, "jogador": 1}]), porta, 2000, [(0, EM_CENA)],
            [(1000, lambda m: m.ajustar({"tipo_do_r2_ao_puxar": "Solto"}))])
    escritas = _gatilhos(porta)
    assert [(modo, params) for _, _, modo, params, _ in escritas] == [ARCO, ("Off", [])]
    assert 1000 <= escritas[1][0] < 1100


@pytest.mark.parametrize("opcoes", [{"forca_geral": 0}, {"canal_gatilho": False}])
def test_a_forca_em_zero_e_o_canal_calado_nao_mandam_o_arco(opcoes: dict[str, Any]) -> None:
    porta = EscritasDeMentira()
    _correr(_motor(opcoes), porta, 3000, [(0, EM_CENA)])
    assert not porta.de("gatilho.set")


def test_a_forca_da_janela_escala_o_arco() -> None:
    porta = EscritasDeMentira()
    _correr(_motor({"forca_geral": 50}, [{"uniq": UM, "jogador": 1}]), porta, 500, [(0, EM_CENA)])
    assert [(modo, params) for _, _, modo, params, _ in _gatilhos(porta)] == [
        ("Bow", [1, 7, 2, 2])]


def test_o_controle_que_liga_depois_do_inicio_ganha_o_arco_e_o_que_sai_e_volta_o_recupera() -> None:
    porta = EscritasDeMentira()
    um, dois = {"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}
    _correr(_motor(controles=[um]), porta, 6000, [(0, EM_CENA)],
            [(1000, lambda m: m.controles([um, dois])),
             (3000, lambda m: m.controles([dois])),
             (4000, lambda m: m.controles([um, dois]))])
    assert [m for m, _ in _viradas(_gatilhos(porta, DOIS))] == ["Bow"]
    assert [(m, round(t, -1)) for m, t in _viradas(_gatilhos(porta, UM))] == [
        ("Bow", 0), ("Off", 3000), ("Bow", 4000)]
    assert round(_viradas(_gatilhos(porta, DOIS))[0][1], -1) == 1000


@pytest.mark.parametrize("devolve", [False, True])
def test_ao_sair_do_jogo_a_receita_se_vai_o_gatilho_volta_ao_perfil_e_o_laco_repousa(
        devolve: bool) -> None:
    porta = EscritasDeMentira(devolve=devolve)
    motor = _motor(controles=[{"uniq": UM, "jogador": 1}])
    universal = servidor.carregar_o_universal()
    saida = _correr(motor, porta, 1000, [(0, EM_CENA)])
    assert [modo for _, _, modo, _, _ in _gatilhos(porta)] == ["Bow"]
    assert not motor.repousa()

    async def sair() -> None:
        motor.evento(*SEM_JOGO)
        motor.trocar(universal)
        for k in range(1, 5):
            t = 1000 + k * TIQUE
            porta.agora = t
            await saida.aplicar(t, motor.passo(t))

    asyncio.run(sair())
    assert [modo for _, _, modo, _, _ in _gatilhos(porta)] == ["Bow", "Off"]
    assert motor.repousa()
    assert saida.prazo_ms(1100.0) is None


class PortaQueCala(EscritasDeMentira):
    """O Modo Nativo, ou o jogo mais forte: a porta recusa todo ``gatilho.set`` com ``-32011``."""

    def __init__(self) -> None:
        super().__init__()
        self.recusas = 0

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "gatilho.set":
            self.recusas += 1
            raise Recusa("no Modo Nativo o jogo fala direto com o controle", -32011)
        return await super().pedir(metodo, params)


def test_a_porta_que_recusa_o_gatilho_nao_e_pedida_de_novo_enquanto_o_arco_continuar() -> None:
    porta = PortaQueCala()
    _correr(_motor(), porta, 12_000, [(0, EM_CENA)])
    assert porta.recusas == len(UNIQS)


def test_o_arco_e_o_gatilho_do_jogo_convivem_pelo_mais_forte_na_linha_gravada() -> None:
    from test_o_universal import TatoVivoDeMentira

    porta = TatoVivoDeMentira()
    _correr(_motor(controles=[{"uniq": UM, "jogador": 1}]), porta, 5000,
            [(0, EM_CENA), *LINHA_DO_GATILHO])
    assert not porta.recusas
    modos = [(round(t, -2), p["modo"]) for t, p in porta.de("gatilho.set")]
    assert modos == [(0, "Bow"), (500, "Off"), (2000, "Bow"), (2600, "Vibration"),
                     (2700, "Bow"), (3500, "Off")]
