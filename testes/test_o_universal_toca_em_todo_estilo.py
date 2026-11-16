"""O Modo imersão toca em todo estilo (16/11/2026).

O Som no corpo e os Gatilhos que vibram são da extensão: cada controle que sente recebe o
``corpo.ligar`` da porta, renovado antes do prazo, em todo preset e com toda receita. O coração, o
alívio, o susto e o peso da mira seguem só no Terror. Vale de um a quatro controles, na mesa
misturada de cabo e rádio, em qualquer ordem, com o controle saindo e voltando.
"""
from __future__ import annotations

import asyncio
import json
import random
from itertools import pairwise
from typing import Any

import pytest
from apoio import DOIS, QUATRO, RAIZ, TRES, UM, EscritasDeMentira, Recusa
from test_o_universal import TIQUE

import opcoes as ajustes
import servidor
from motor.saida import ATE_MS_DO_CORPO, RENOVA_MS
from receita import estilos

UNIQS = (UM, DOIS, TRES, QUATRO)
PADRAO = {"som_no_corpo": 0.7, "gatilhos": {"tipo": "tranco", "forca": 0.7}}
DO_TERROR = estilos.CORACAO | estilos.SUSTO | estilos.MIRA


def _mesa(transportes: str, ordem: int = 0) -> list[dict[str, Any]]:
    controles = [{"uniq": u, "jogador": j, "transporte": "usb" if t == "c" else "bt"}
                 for j, (u, t) in enumerate(zip(UNIQS, transportes, strict=False), 1)]
    random.Random(ordem).shuffle(controles)
    return controles


class PortaDoCorpo(EscritasDeMentira):
    """A porta de mentira com os controles e o ``corpo.ligar`` da porta de verdade: o prazo de 1 a
    10000 ms, o tipo um dos padrões dos motores, o vazio que solta e o ``-32011`` do Modo Nativo
    nos controles de ``nativos``."""

    def __init__(self, controles: list[dict[str, Any]], nativos: frozenset[str] = frozenset(),
                 sem_o_metodo: bool = False) -> None:
        super().__init__(com_haptica=True, com_som=True)
        self.controles = controles
        self.nativos = nativos
        self.sem_o_metodo = sem_o_metodo
        self.vivos: dict[str, tuple[dict[str, Any], float]] = {}
        self.tentativas: list[tuple[float, str]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "controles.lista":
            return {"controles": self.controles}
        if metodo in ("acessorios.estado", "eventos.assinar", "eventos.desassinar"):
            return {"status": "ok"}
        if metodo == "corpo.ligar":
            self.tentativas.append((self.agora, params["uniq"]))
            if self.sem_o_metodo:
                raise Recusa("método desconhecido: corpo.ligar", -32601)
            assert isinstance(params["ate_ms"], int) and 0 < params["ate_ms"] <= 10_000
            assert 0.0 <= params.get("som_no_corpo", 0.0) <= 1.0
            gatilhos = params.get("gatilhos")
            if gatilhos is not None:
                assert gatilhos["tipo"] in set(ajustes.TIPOS_DOS_GATILHOS.values())
                assert 0.0 <= gatilhos["forca"] <= 1.0
            if params["uniq"] in self.nativos:
                erro = Recusa("no Modo Nativo o jogo fala direto com o controle", -32011)
                erro.dados = {"canal": "corpo", "modo": "nativo"}  # type: ignore[attr-defined]
                raise erro
            if "som_no_corpo" in params or gatilhos is not None:
                self.vivos[params["uniq"]] = (params, self.agora + params["ate_ms"])
            else:
                self.vivos.pop(params["uniq"], None)
        return await super().pedir(metodo, params)

    def corpos(self, uniq: str | None = None) -> list[tuple[float, dict[str, Any]]]:
        return [(t, p) for t, p in self.de("corpo.ligar") if uniq is None or p["uniq"] == uniq]

    def vivo_em(self, uniq: str, t: float) -> dict[str, Any] | None:
        vivo = self.vivos.get(uniq)
        return vivo[0] if vivo is not None and vivo[1] > t else None


def _extensao(porta: PortaDoCorpo, estilo: str | None = None) -> servidor.Extensao:
    extensao = servidor.Extensao(porta, servidor.carregar_o_universal())  # type: ignore[arg-type]
    asyncio.run(extensao.atualizar_os_controles())
    asyncio.run(extensao.ao_evento({"method": "evento", "params": {
        "topico": "jogo.estilo", "nome": "jogo.estilo", "uniq": None,
        "dados": {"estilo": estilo}}}))
    extensao.jogo = "steam_app_1"
    return extensao


def _correr(extensao: servidor.Extensao, porta: PortaDoCorpo, de_ms: float, ate_ms: float) -> None:
    async def correr() -> None:
        k = 0
        while (t := de_ms + k * TIQUE) <= ate_ms:
            porta.agora = t
            await extensao.saida.aplicar(t, extensao.motor.passo(t))
            k += 1

    asyncio.run(correr())


@pytest.mark.parametrize("preset", [*estilos.PRESETS, None])
def test_nenhum_preset_cala_o_corpo_e_o_do_terror_fica_no_terror(preset: str | None) -> None:
    sem = estilos.do_preset(preset) if preset is not None else (frozenset(), {})
    assert not sem[0] & estilos.CORPO
    assert estilos.CORPO == frozenset(ajustes.CANAL_DO_CORPO)
    if preset not in (estilos.TERROR, None):
        assert DO_TERROR <= sem[0]


@pytest.mark.parametrize("estilo", [None, "fps", "terror", "corrida", "ritmo", "aventura", "luta"])
def test_o_geral_e_todo_estilo_ligam_o_corpo_nos_quatro_controles_e_renovam_antes_do_prazo(
        estilo: str | None) -> None:
    porta = PortaDoCorpo(_mesa("cbcb"))
    extensao = _extensao(porta, estilo)
    assert extensao.preset == estilos.preset_do_jogo(estilo)
    _correr(extensao, porta, 0, 12_000)
    for uniq in UNIQS:
        corpos = porta.corpos(uniq)
        assert corpos and all({k: v for k, v in p.items() if k not in ("uniq", "ate_ms")} == PADRAO
                              and p["ate_ms"] == ATE_MS_DO_CORPO for _, p in corpos)
        instantes = [t for t, _ in corpos]
        assert instantes[0] == 0
        assert all(b - a <= RENOVA_MS + TIQUE + 1
                   for a, b in pairwise(instantes))
        assert all(porta.vivo_em(uniq, t) for t in range(0, 12_000, 250))
    presentes = extensao.presentes()
    assert {ajustes.SOM_NO_CORPO, ajustes.GATILHOS_QUE_VIBRAM} <= set(presentes)


@pytest.mark.parametrize("transportes", ["cccc", "cccb", "ccbb", "cbbb", "bbbb", "c", "bb"])
@pytest.mark.parametrize("ordem", [0, 1, 2])
def test_a_mesa_misturada_em_qualquer_ordem_liga_cada_controle(transportes: str,
                                                               ordem: int) -> None:
    mesa = _mesa(transportes, ordem)
    porta = PortaDoCorpo(mesa)
    extensao = _extensao(porta)
    _correr(extensao, porta, 0, 3000)
    assert {p["uniq"] for _, p in porta.corpos()} == {c["uniq"] for c in mesa}


def test_o_controle_que_sai_e_solto_e_o_que_volta_liga_de_novo() -> None:
    mesa = _mesa("cbcb")
    porta = PortaDoCorpo(mesa)
    extensao = _extensao(porta)
    _correr(extensao, porta, 0, 1000)
    porta.controles = [c for c in mesa if c["uniq"] != TRES]
    asyncio.run(extensao.atualizar_os_controles())
    _correr(extensao, porta, 1000 + TIQUE, 4000)
    soltura = [p for t, p in porta.corpos(TRES) if t > 1000]
    assert soltura == [{"uniq": TRES, "ate_ms": ATE_MS_DO_CORPO}]
    porta.controles = mesa
    asyncio.run(extensao.atualizar_os_controles())
    _correr(extensao, porta, 4000 + TIQUE, 5000)
    assert porta.vivo_em(TRES, 5000) is not None


def test_a_janela_muda_o_que_o_corpo_pede_por_controle() -> None:
    porta = PortaDoCorpo(_mesa("cbcb"))
    extensao = _extensao(porta)
    asyncio.run(extensao.nivelar(ajustes.CONTROLE_DA_FORCA, "jogador-2", "50"))
    asyncio.run(extensao.sentir("jogador-3", False))
    extensao.motor.opcoes.update({ajustes.TIPO_DOS_GATILHOS: "Coice", ajustes.FORCA: 50})
    pedidos = extensao.pedidos_do_corpo()
    assert TRES not in pedidos
    assert pedidos[UM] == {"som_no_corpo": 0.35, "gatilhos": {"tipo": "coice", "forca": 0.35}}
    assert pedidos[DOIS] == {"som_no_corpo": 0.175, "gatilhos": {"tipo": "coice", "forca": 0.175}}
    extensao.motor.opcoes.update({"canal_haptica": False})
    assert set(extensao.pedidos_do_corpo()[UM]) == {"gatilhos"}
    extensao.motor.opcoes.update({"canal_haptica": True, "canal_motor": False})
    assert set(extensao.pedidos_do_corpo()[UM]) == {"som_no_corpo"}
    extensao.motor.opcoes.update({"canal_motor": True, ajustes.SOM_NO_CORPO: 0,
                                  ajustes.GATILHOS_QUE_VIBRAM: 0})
    assert extensao.pedidos_do_corpo() == {}
    extensao.motor.opcoes.update({ajustes.SOM_NO_CORPO: 70, ajustes.FORCA: 0})
    assert extensao.pedidos_do_corpo() == {}


def test_o_controle_calado_no_meio_recebe_o_vazio_e_nada_mais() -> None:
    porta = PortaDoCorpo(_mesa("cbcb"))
    extensao = _extensao(porta)
    _correr(extensao, porta, 0, 1000)
    asyncio.run(extensao.sentir("jogador-2", False))
    _correr(extensao, porta, 1000 + TIQUE, 8000)
    depois = [p for t, p in porta.corpos(DOIS) if t > 1000]
    assert depois == [{"uniq": DOIS, "ate_ms": ATE_MS_DO_CORPO}]
    assert porta.vivo_em(DOIS, 8000) is None and porta.vivo_em(UM, 8000) is not None


def test_o_modo_nativo_recusa_conta_no_diario_e_tenta_de_novo_so_na_renovacao(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaDoCorpo([{"uniq": UM, "jogador": 1, "cor": "Cosmic Red"},
                          {"uniq": DOIS, "jogador": 2, "cor": "Starlight Blue"}],
                         nativos=frozenset({DOIS}))
    extensao = _extensao(porta)
    _correr(extensao, porta, 0, 6000)
    assert porta.corpos(DOIS) == []
    tentativas = [t for t, u in porta.tentativas if u == DOIS]
    assert len(tentativas) == 3 and tentativas[0] == 0
    assert all(b - a >= RENOVA_MS for a, b in pairwise(tentativas))
    capsys.readouterr()
    extensao.fechar_o_minuto()
    linha = capsys.readouterr().err
    assert "Cosmic Red tocou gatilhos que vibram 3, som no corpo 3" in linha
    assert "Starlight Blue tocou nada; não tocou: nativo 3" in linha


def test_a_porta_sem_o_corpo_cala_os_dois_e_diz_uma_vez() -> None:
    porta = PortaDoCorpo(_mesa("cb"), sem_o_metodo=True)
    extensao = _extensao(porta)
    diario: list[str] = []
    extensao.saida._diario = diario.append
    _correr(extensao, porta, 0, 6000)
    assert extensao.saida.sem_corpo and porta.corpos() == []
    assert len(porta.tentativas) == 1
    assert len([f for f in diario if "corpo" in f]) == 1


def test_a_saida_da_extensao_solta_o_corpo_de_cada_controle() -> None:
    porta = PortaDoCorpo(_mesa("cbcb"))
    extensao = _extensao(porta)
    _correr(extensao, porta, 0, 500)
    asyncio.run(extensao.saida.soltar_tudo(600))
    assert all(porta.vivo_em(u, 600) is None for u in UNIQS)
    assert extensao.saida.pedidos_do_corpo is not None


def test_o_manifesto_pede_o_corpo_e_a_janela_tem_os_dois_com_o_padrao_da_extensao() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    assert "escrever:corpo" in manifesto["permissoes"]  # (noqa-acento)
    opcoes = {o["id"]: o for o in manifesto["opcoes"]}  # (noqa-acento)
    assert opcoes[ajustes.SOM_NO_CORPO]["padrao"] == ajustes.PADRAO_DO_SOM_NO_CORPO  # (noqa-acento)
    assert opcoes[ajustes.GATILHOS_QUE_VIBRAM]["padrao"] == ajustes.PADRAO_DOS_GATILHOS  # (noqa-acento)
    tipo = opcoes[ajustes.TIPO_DOS_GATILHOS]
    assert tipo["escolhas"] == list(ajustes.TIPOS_DOS_GATILHOS)
    assert tipo["padrao"] == ajustes.TIPO_PADRAO_DOS_GATILHOS  # (noqa-acento)
    for ident in (ajustes.SOM_NO_CORPO, ajustes.GATILHOS_QUE_VIBRAM, ajustes.TIPO_DOS_GATILHOS):
        assert opcoes[ident]["grupo"] == "Efeitos"
    vibracao = pytest.importorskip(
        "hefesto_dualsense4unix.daemon.subsystems.padroes_de_vibracao")
    assert set(ajustes.TIPOS_DOS_GATILHOS.values()) <= set(vibracao.PADROES)
    do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto")
    assert "escrever:corpo" in do_hefesto.ler_manifesto(RAIZ).permissoes
