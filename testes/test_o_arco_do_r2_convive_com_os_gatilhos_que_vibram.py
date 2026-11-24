"""O arco do R2 do Dungeons II convive com os Gatilhos que vibram (24/11/2026).

Com a receita do jogo e nenhum golpe, a linha do minuto diz «gatilhos 1, gatilhos que vibram 24,
som no corpo 24». Os 24 são o ``corpo.ligar`` de cada controle renovado a cada 2,5 s: um pedido
aos motores do tato vivo (o padrão no aperto do L2 e do R2), sem lado nem bloco de gatilho, que
nunca vira ``gatilho.set``. O «gatilhos 1» é o arco do R2 (``r2_ao_puxar``) que nasceu com o jogo
e segue vivo: a mesma identidade não conta de novo. A cena «jogo aberto, nenhum golpe, um golpe,
silêncio» mostra o que a porta recebe para o R2 de cada controle da mesa, de P1 a P4, no cabo e
no rádio, com a porta que devolve e a que não devolve.
"""
from __future__ import annotations

import asyncio
from itertools import pairwise
from typing import Any

import pytest
from apoio import DOIS, QUATRO, TRES, UM
from test_a_receita_minecraft_dungeons_ii import _receita
from test_o_universal import TIQUE, Evento, entradas, rumble
from test_o_universal_toca_em_todo_estilo import PortaDoCorpo

import opcoes as ajustes
import servidor
from motor.saida import ATE_MS_DO_CORPO, ATE_MS_DO_GATILHO_CONTINUO, RENOVA_MS

UNIQS = (UM, DOIS, TRES, QUATRO)
CORES = ("Cosmic Red", "Starlight Blue", "Midnight Black", "Nova Pink")
TRANSPORTES = ("usb", "bt", "usb", "bt")
ARCO = ("Bow", [1, 7, 4, 4])
MINUTO_MS = 60_000.0
GOLPE_MS = 61_000.0
FIM_MS = 70_000.0
EM_CENA: Evento = ("perfil.jogo", "perfil.trocou", None, {
    "perfil": "Jogo", "jogo": "steam_app_1912410", "em_cena": True, "estilo": None,
    "controles": [], "t": 1.0})
CAMPOS_DO_CORPO = {"uniq", "som_no_corpo", "gatilhos", "ate_ms"}


class PortaComOGatilho(PortaDoCorpo):
    """A porta do corpo que também responde ``devolve: true`` ao ``gatilho.set`` com prazo."""

    def __init__(self, controles: list[dict[str, Any]], devolve: bool) -> None:
        super().__init__(controles)
        self.devolve = devolve


def _mesa() -> list[dict[str, Any]]:
    return [{"uniq": u, "jogador": j, "transporte": t, "cor": c}
            for j, (u, t, c) in enumerate(zip(UNIQS, TRANSPORTES, CORES, strict=True), 1)]


def _golpe(uniq: str, t: float, transporte: str) -> list[tuple[float, Evento]]:
    return [(t, entradas(uniq, 200, transporte=transporte)), (t + 80, rumble(uniq, 180)),
            (t + 200, rumble(uniq, 0)), (t + 300, entradas(uniq, 0, transporte=transporte))]


def _cena(alvo: str, devolve: bool, capsys: pytest.CaptureFixture[str]
          ) -> tuple[PortaComOGatilho, list[str]]:
    """A extensão com a receita do Dungeons II: o jogo entra em 0, ninguém bate até o minuto
    fechar em 60 s, o R2 de ``alvo`` dá um golpe em 61 s, e o silêncio segue até 70 s."""
    porta = PortaComOGatilho(_mesa(), devolve)
    extensao = servidor.Extensao(porta, _receita())  # type: ignore[arg-type]
    asyncio.run(extensao.atualizar_os_controles())
    extensao.jogo = "steam_app_1912410"
    transporte = TRANSPORTES[UNIQS.index(alvo)]
    fila = sorted([(0.0, EM_CENA), *_golpe(alvo, GOLPE_MS, transporte)], key=lambda e: e[0])
    linhas: list[str] = []

    async def correr() -> None:
        k = 0
        fechou = False
        while (t := k * TIQUE) <= FIM_MS:
            if not fechou and t >= MINUTO_MS:
                capsys.readouterr()
                extensao.fechar_o_minuto()
                linhas.append(capsys.readouterr().err)
                fechou = True
            while fila and fila[0][0] <= t + 1e-6:
                extensao.motor.evento(*fila.pop(0)[1])
            porta.agora = t
            await extensao.saida.aplicar(t, extensao.motor.passo(t))
            k += 1

    asyncio.run(correr())
    capsys.readouterr()
    extensao.fechar_o_minuto()
    linhas.append(capsys.readouterr().err)
    return porta, linhas


def _r2(porta: PortaComOGatilho, uniq: str) -> list[tuple[float, str, list[int], Any]]:
    escritas = [(t, p) for t, p in porta.de("gatilho.set") if p["uniq"] == uniq]
    assert all(p["lado"] == "direito" for _, p in escritas)
    return [(t, p["modo"], p["params"], p.get("ate_ms")) for t, p in escritas]


def _no_gatilho(r2: list[tuple[float, str, list[int], Any]], t: float) -> str | None:
    """O que a porta guarda no R2 em ``t``: a última escrita, enquanto o prazo dela vale."""
    antes = [e for e in r2 if e[0] <= t]
    if not antes:
        return None
    t0, modo, _params, ate = antes[-1]
    if modo == "Off" or (ate is not None and t >= t0 + ate):
        return None
    return modo


@pytest.mark.parametrize("devolve", [False, True])
@pytest.mark.parametrize("alvo", UNIQS)
def test_sem_golpe_o_arco_fica_no_r2_e_o_corpo_nunca_escreve_no_gatilho(
        alvo: str, devolve: bool, capsys: pytest.CaptureFixture[str]) -> None:
    porta, linhas = _cena(alvo, devolve, capsys)
    for uniq, cor in zip(UNIQS, CORES, strict=True):
        r2 = _r2(porta, uniq)
        antes_do_golpe = [e for e in r2 if e[0] < GOLPE_MS]
        assert {(m, tuple(p), a) for _, m, p, a in antes_do_golpe} == {
            (ARCO[0], tuple(ARCO[1]), ATE_MS_DO_GATILHO_CONTINUO)}
        instantes = [t for t, *_ in antes_do_golpe]
        assert instantes[0] == 0
        assert all(RENOVA_MS <= b - a < RENOVA_MS + 2 * TIQUE for a, b in pairwise(instantes))
        assert all(_no_gatilho(r2, t) == "Bow" for t in range(0, int(GOLPE_MS), 100))
        corpos = porta.corpos(uniq)
        assert corpos and all(set(p) <= CAMPOS_DO_CORPO and p["ate_ms"] == ATE_MS_DO_CORPO
                              and set(p["gatilhos"]) == {"tipo", "forca"}
                              and p["gatilhos"]["tipo"] in set(ajustes.TIPOS_DOS_GATILHOS.values())
                              for _, p in corpos)
        no_minuto = [t for t, _ in corpos if t < MINUTO_MS]
        assert len(no_minuto) == 24
        assert f"{cor} tocou gatilhos 1, gatilhos que vibram 24, som no corpo 24" in linhas[0]
    assert "não tocou" not in linhas[0]


@pytest.mark.parametrize("devolve", [False, True])
@pytest.mark.parametrize("alvo", UNIQS)
def test_o_golpe_toca_o_impacto_por_cima_o_arco_volta_e_fica_no_silencio(
        alvo: str, devolve: bool, capsys: pytest.CaptureFixture[str]) -> None:
    porta, linhas = _cena(alvo, devolve, capsys)
    r2 = _r2(porta, alvo)
    depois = [e for e in r2 if e[0] >= GOLPE_MS]
    impacto, volta = depois[0], depois[1]
    assert (impacto[1], impacto[3]) == ("Vibration", 150)
    assert GOLPE_MS <= impacto[0] < GOLPE_MS + 200
    assert (volta[1], volta[2], volta[3]) == (*ARCO, ATE_MS_DO_GATILHO_CONTINUO)
    assert volta[0] - impacto[0] in range(150, 170)
    assert {(m, a) for _, m, _, a in depois[1:]} == {("Bow", ATE_MS_DO_GATILHO_CONTINUO)}
    assert all(_no_gatilho(r2, t) == "Bow" for t in range(int(volta[0]) + 1, int(FIM_MS), 100))
    for outro in set(UNIQS) - {alvo}:
        assert {m for _, m, _, _ in _r2(porta, outro)} == {"Bow"}
        assert all(_no_gatilho(_r2(porta, outro), t) == "Bow"
                   for t in range(0, int(FIM_MS), 100))
    cor = CORES[UNIQS.index(alvo)]
    assert f"{cor} tocou gatilhos 2, gatilhos que vibram 4, som no corpo 4" in linhas[1]
