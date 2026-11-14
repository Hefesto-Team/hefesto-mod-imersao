"""O Modo imersão segue o estilo do jogo (14/11/2026).

O ``jogo.estilo`` do Hefesto escolhe o preset do universal: num jogo de tiro não há coração nem
susto, e há o golpe com lado; num de terror, há os dois. A opção «Estilo» troca o preset à mão, e
um Hefesto que não diz o estilo deixa o universal como era. Vale para os quatro controles.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from apoio import QUATRO_CONTROLES, RAIZ, UM, EscritasDeMentira
from test_o_universal import _correr, _universal, microfone, na_mao, som

import servidor
from receita import estilos

TENSO_E_SUSTO = ([(t, microfone(UM, 0.01)) for t in range(0, 20_000, 500)]
                 + na_mao(UM, 20_000) + [(18_000, som("direito", 0.45, 1234.5))])


def _tocou(preset: str | None) -> tuple[set[str], int, int]:
    motor = _universal(QUATRO_CONTROLES)
    if preset is not None:
        motor.estilo(*estilos.do_preset(preset))
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(motor, porta, 19_000, TENSO_E_SUSTO)
    haptica = {p["id"] for _, p in porta.de("haptica.tocar") if p["forca"] > 0}  # (noqa-acento)
    golpes = [p for _, p in porta.de("vibracao.set") if p["fraco"] or p["forte"]]
    return haptica, len(porta.de("som.tocar")), len(golpes)


def test_com_o_jogo_de_tiro_nao_ha_coracao_nem_susto_e_o_golpe_fica() -> None:
    haptica, sons, golpes = _tocou(estilos.preset_do_jogo("fps"))
    assert "coracao" not in haptica and "susto" not in haptica  # (noqa-acento)
    assert sons == 0
    assert golpes > 0


def test_com_o_jogo_de_terror_ha_coracao_e_susto() -> None:
    haptica, sons, _golpes = _tocou(estilos.preset_do_jogo("terror"))
    assert {"coracao", "susto"} <= haptica  # (noqa-acento)
    assert sons > 0


def test_sem_o_estilo_dito_o_universal_toca_como_antes() -> None:
    assert _tocou(None) == _tocou(estilos.TERROR)


@pytest.mark.parametrize("estilo", ["corrida", "luta", "aventura", "plataforma", "ritmo", None,
                                    "inventado"])
def test_nenhum_outro_estilo_tem_coracao_nem_susto(estilo: str | None) -> None:
    haptica, sons, _golpes = _tocou(estilos.preset_do_jogo(estilo))
    assert not {"coracao", "susto"} & haptica  # (noqa-acento)
    assert sons == 0


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"status": "ok"}


def _estilo(chave: str | None) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": "jogo.estilo", "nome": "jogo.estilo",
                                           "uniq": UM, "dados": {"estilo": chave, "jogo": None,
                                                                 "controles": [], "t": 1.0}}}


def test_a_extensao_le_o_jogo_estilo_troca_o_preset_e_o_agora_diz_qual() -> None:
    async def corrida() -> list[tuple[str | None, frozenset[str], list[dict[str, str]]]]:
        extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal())  # type: ignore[arg-type]
        vistos = [(extensao.preset, extensao.motor.sem_do_estilo, extensao.linhas())]
        for chave in ("fps", "terror"):
            await extensao.ao_evento(_estilo(chave))
            vistos.append((extensao.preset, extensao.motor.sem_do_estilo, extensao.linhas()))
        await extensao.ao_evento({"method": "evento", "params": {
            "topico": "extensao.opcao", "nome": "extensao.opcao", "uniq": None,
            "dados": {"id": estilos.OPCAO, "valor": estilos.RITMO}}})
        vistos.append((extensao.preset, extensao.motor.sem_do_estilo, extensao.linhas()))
        return vistos

    antes, tiro, terror, ritmo = asyncio.run(corrida())
    assert antes[0] is None and antes[1] == frozenset()
    assert not [linha for linha in antes[2] if linha["rotulo"] == "Estilo"]
    assert tiro[0] == estilos.TIRO and "coracao" in tiro[1]  # (noqa-acento)
    assert {"rotulo": "Estilo", "valor": "Tiro"} in tiro[2]
    assert terror[0] == estilos.TERROR and terror[1] == frozenset()
    assert ritmo[0] == estilos.RITMO and estilos.IMPACTO <= ritmo[1]


def test_o_manifesto_pede_o_estilo_e_a_janela_tem_a_escolha() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    assert "ler:jogo.estilo" in manifesto["permissoes"]  # (noqa-acento)
    opcao = next(o for o in manifesto["opcoes"] if o["id"] == estilos.OPCAO)
    assert tuple(opcao["escolhas"]) == estilos.ESCOLHAS
    assert opcao["padrao"] == estilos.PELO_JOGO
    assert "jogo.estilo" in servidor.topicos_assinados(servidor.carregar_o_universal())


def _por_controle(preset: str) -> tuple[dict[str, int], dict[str, set[str]]]:
    motor = _universal(QUATRO_CONTROLES)
    motor.estilo(*estilos.do_preset(preset))
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(motor, porta, 19_000, TENSO_E_SUSTO)
    golpe: dict[str, int] = {}
    for _, p in porta.de("vibracao.set"):
        golpe[p["uniq"]] = max(golpe.get(p["uniq"], 0), p["fraco"], p["forte"])
    haptica: dict[str, set[str]] = {}
    for _, p in porta.de("haptica.tocar"):
        if p["forca"] > 0:
            haptica.setdefault(p["uniq"], set()).add(p["id"])
    return golpe, haptica


@pytest.mark.parametrize("preset", [estilos.CORRIDA, estilos.AVENTURA, estilos.RITMO,
                                    estilos.GERAL])
def test_o_golpe_com_lado_sai_pela_forca_do_preset_nos_quatro_controles(preset: str) -> None:
    inteiro, terror = _por_controle(estilos.TERROR)
    suave, sem = _por_controle(preset)
    _sem, escalas = estilos.do_preset(preset)
    todos = {str(c["uniq"]) for c in QUATRO_CONTROLES}
    assert set(inteiro) == set(suave) == todos
    assert all({"coracao", "susto"} <= terror[u] for u in todos)  # (noqa-acento)
    assert not sem
    for uniq in todos:
        assert suave[uniq] == pytest.approx(inteiro[uniq] * escalas["motor_direito"], abs=2)
