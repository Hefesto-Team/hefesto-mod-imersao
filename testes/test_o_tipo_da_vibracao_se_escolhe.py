"""O tipo da vibração de cada efeito que vibra e o efeito do L2 e do R2 se escolhem na janela, em
toda receita pelo mesmo ``$tipo_do_*``; a receita que não cita toca o de antes, e o botão de testar
toca uma vez em cada controle, de 1 a 4, pelo cabo e pelo rádio."""
from __future__ import annotations

import asyncio
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest
from apoio import QUATRO_CONTROLES, RAIZ, UM, EscritasDeMentira
from test_o_susto_se_ajusta import (
    LINHA,
    MESAS,
    PortaDaTela,
    PortaQueGuardaOsRegistros,
    _acao,
    _linha,
)
from test_o_universal import _correr, _universal, entradas, rumble

import opcoes as ajustes
import servidor
from motor import efeitos as catalogo
from motor.laco import Motor
from receita.formato import ler_receita

AMOSTRAS_MS = range(0, 400, 5)
TIPOS_DOS_EFEITOS = ("tipo_do_coracao", "tipo_do_alivio", "tipo_do_golpe", "tipo_do_susto")


def _envelope(padrao: str) -> tuple[float, ...]:
    return tuple(round(catalogo.envelope(padrao, t, catalogo.BPM_PADRAO), 4) for t in AMOSTRAS_MS)


def test_cada_tipo_tem_forma_propria_e_a_duracao_declarada() -> None:
    uma_vez = {t: catalogo.id_do_padrao(f, False) for t, f in catalogo.TIPOS_DA_VIBRACAO.items()}
    for (tipo, padrao), (outro, de_outro) in combinations(uma_vez.items(), 2):
        assert _envelope(padrao) != _envelope(de_outro), (tipo, outro)
    for padrao in uma_vez.values():
        forma = catalogo.PADROES[padrao]
        assert forma.dura_ms == max(g.inicio_ms + g.dura_ms for g in forma.golpes)
        assert catalogo.padrao(padrao, 600).dura_ms == 600
    assert catalogo.PADROES["coracao"].golpes == catalogo.FORMAS["batida"]  # (noqa-acento)
    assert catalogo.PADROES["susto"].golpes == catalogo.FORMAS["pancada"]
    assert catalogo.PADROES["estalo"].golpes == catalogo.FORMAS["estalo"]


def test_as_escolhas_do_gatilho_sao_os_nomes_da_aba_gatilhos_do_hefesto() -> None:
    specs = pytest.importorskip("hefesto_dualsense4unix.app.actions.trigger_specs")
    da_tela = {p.name: p.label for p in specs.PRESETS}
    for rotulo, fabrica in catalogo.TIPOS_DO_GATILHO.items():
        nome, valores = fabrica(8)
        assert da_tela[nome] == rotulo
        preset = next(p for p in specs.PRESETS if p.name == nome)
        assert len(valores) == len(preset.params)
        for valor, param in zip(valores, preset.params, strict=True):
            assert param.min_value <= valor <= param.max_value, (rotulo, param.name)


def _so_o_susto(porta: Any, uniq: str) -> list[dict[str, Any]]:
    return [p for _, p in porta.de("haptica.tocar") if p["uniq"] == uniq and p["forca"]
            and p["id"] not in ("coracao", "batida_ritmo")]  # (noqa-acento)


@pytest.mark.parametrize("mesa", sorted(MESAS))
def test_o_tipo_do_susto_chega_ao_pedido_da_porta_em_cada_controle(mesa: str) -> None:
    controles = MESAS[mesa]
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    opcoes = {"tipo_do_susto": "Tremor", "duracao_do_susto": 600}
    _correr(_universal(controles, opcoes), porta, 19_000, _linha(controles[0]["uniq"]))
    tremor = catalogo.id_do_padrao("tremor", False)
    assert porta.golpes[tremor] == catalogo.golpes(catalogo.padrao(tremor, 600))
    for uniq in sorted(c["uniq"] for c in controles):
        assert {p["id"] for p in _so_o_susto(porta, uniq)} == {tremor}


def test_a_escolha_fora_da_lista_vale_o_padrao_da_entrada() -> None:
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    _correr(_universal(opcoes={"tipo_do_susto": "Inventado"}), porta, 19_000, LINHA)
    assert {p["id"] for p in _so_o_susto(porta, UM)} == {"susto"}


@pytest.mark.parametrize("transporte", ["usb", "bt"])
@pytest.mark.parametrize(("escolha", "modo"), [("Vibração", "Vibration"), ("Galope", "Galloping"),
                                                ("Arco", "Bow"), ("Disparo", "Weapon")])
def test_o_efeito_do_r2_escolhido_chega_ao_gatilho_set(transporte: str, escolha: str,
                                                       modo: str) -> None:
    motor, porta = _universal(opcoes={"tipo_do_r2": escolha}), EscritasDeMentira()
    _correr(motor, porta, 1000, [(100, entradas(UM, 200, transporte=transporte)),
                                 (200, rumble(UM, 180)), (300, rumble(UM, 0))])
    gatilhos = [(p["lado"], p["modo"]) for _, p in porta.de("gatilho.set")]
    assert gatilhos[0] == ("direito", modo) and gatilhos[1] == ("direito", "Off")


def _sem_os_tipos(bruto: dict[str, Any]) -> bytes:
    for efeito in bruto["efeitos"].values():
        efeito.pop("tipo", None)
    for nome in [n for n in bruto["entradas"] if n.startswith("tipo_do_")]:
        del bruto["entradas"][nome]
    return json.dumps(bruto).encode()


def _escritas(motor: Motor, controles: list[dict[str, Any]]) -> list[tuple[float, str, Any]]:
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    motor.controles(controles)
    _correr(motor, porta, 19_000, [*_linha(controles[0]["uniq"]), (100, entradas(UM, 200)),
                                   (200, rumble(UM, 180)), (300, rumble(UM, 0))])
    return [(round(t, 3), m, json.dumps(p, sort_keys=True)) for t, m, p in porta.escritas]


@pytest.mark.parametrize("controles", [MESAS["um"], QUATRO_CONTROLES], ids=["um", "quatro"])
def test_a_receita_que_nao_cita_o_tipo_toca_igual_a_de_antes(controles: list[Any]) -> None:
    bruto = json.loads((RAIZ / "receitas" / "universal.json").read_text(encoding="utf-8"))
    sem_citar = Motor(ler_receita(_sem_os_tipos(bruto)), None)
    no_padrao = Motor(servidor.carregar_o_universal(), None)
    assert _escritas(sem_citar, controles) == _escritas(no_padrao, controles)


def _testar(acao: str, opcoes: dict[str, Any], controles: list[Any]) -> PortaQueGuardaOsRegistros:
    motor = _universal(controles, opcoes)
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    assert motor.testar(ajustes.TESTES[acao], 50)
    _correr(motor, porta, 1500)
    return porta


@pytest.mark.parametrize("mesa", sorted(MESAS))
def test_o_botao_de_testar_toca_o_tipo_escolhido_uma_vez_em_cada_controle(mesa: str) -> None:
    controles = MESAS[mesa]
    uniqs = sorted(c["uniq"] for c in controles)
    porta = _testar("testar_susto", {"tipo_do_susto": "Onda"}, controles)
    onda = catalogo.id_do_padrao("onda", False)
    for uniq in uniqs:
        assert {p["id"] for _, p in porta.de("haptica.tocar")
                if p["uniq"] == uniq and p["forca"]} == {onda}
    porta = _testar("testar_gatilhos", {"tipo_do_l2": "Arco", "tipo_do_r2": "Metralhadora"},
                    controles)
    for uniq in uniqs:
        ligados = {(p["lado"], p["modo"]) for _, p in porta.de("gatilho.set")
                   if p["uniq"] == uniq and p["modo"] != "Off"}
        assert ligados == {("esquerdo", "Bow"), ("direito", "Machine")}
        assert {p["modo"] for _, p in porta.de("gatilho.set") if p["uniq"] == uniq} >= {"Off"}


@pytest.mark.parametrize("mesa", sorted(MESAS))
@pytest.mark.parametrize(("acao", "tipo"), [("testar_coracao", "Tremor"), ("testar_coracao", "Batida"),
                                            ("testar_alivio", "Onda")])
def test_o_testar_do_que_repete_toca_a_forma_uma_vez_so(mesa: str, acao: str, tipo: str) -> None:
    controles = MESAS[mesa]
    entrada = ajustes.TESTES[acao][0]
    porta = _testar(acao, {entrada: tipo}, controles)
    forma = catalogo.id_do_padrao(catalogo.TIPOS_DA_VIBRACAO[tipo], False)
    assert not catalogo.PADROES[forma].repete
    for uniq in sorted(c["uniq"] for c in controles):
        assert {p["id"] for _, p in porta.de("haptica.tocar")
                if p["uniq"] == uniq and p["forca"]} == {forma}


def test_o_golpe_com_forma_desenha_o_motor_e_o_continuo_segue_reto() -> None:
    def forcas(tipo: str) -> list[int]:
        porta = _testar("testar_golpe", {"tipo_do_golpe": tipo}, MESAS["um"])
        return [p["forte"] for _, p in porta.de("vibracao.set") if p["uniq"] == UM]

    continuo, tremor = forcas("Contínuo"), forcas("Tremor")
    assert len({f for f in continuo if f}) == 1
    ligados = [f for f in tremor if f]
    assert ligados and tremor.count(0) >= 3


def test_cada_tipo_da_janela_e_uma_entrada_de_escolha_das_receitas_com_o_padrao_de_hoje() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    da_janela = {o["id"]: o for o in manifesto["opcoes"] if o["id"].startswith("tipo_do_")}
    assert set(da_janela) == {*TIPOS_DOS_EFEITOS, "tipo_do_l2", "tipo_do_r2"}
    for caminho in (RAIZ / "receitas").rglob("*.json"):
        receita = ler_receita(caminho.read_bytes())
        for nome, entrada in receita.secao("entradas").items():
            if nome in da_janela:
                assert entrada["escolhas"] == da_janela[nome]["escolhas"], (caminho.name, nome)
                assert entrada["padrao"] == da_janela[nome]["padrao"], (caminho.name, nome)  # (noqa-acento)
    assert da_janela["tipo_do_susto"]["padrao"] == "Pancada"  # (noqa-acento)
    assert da_janela["tipo_do_coracao"]["padrao"] == "Batida"  # (noqa-acento)
    assert da_janela["tipo_do_golpe"]["padrao"] == catalogo.CONTINUO  # (noqa-acento)
    assert da_janela["tipo_do_r2"]["padrao"] == da_janela["tipo_do_l2"]["padrao"] == "Vibração"  # (noqa-acento)


@pytest.mark.parametrize(("acao", "efeitos"), [
    ("testar_susto", {"susto_no_tato"}), ("testar_golpe", {"motor_esquerdo", "motor_direito"}),
    ("testar_gatilhos", {"impacto_no_l2", "impacto_no_r2"}), ("testar_coracao", {"coracao"}),  # (noqa-acento)
    ("testar_alivio", {"alivio"})])
def test_o_clique_no_testar_da_janela_toca_o_efeito_em_todo_controle(
        tmp_path: Path, acao: str, efeitos: set[str]) -> None:
    porta = PortaDaTela()

    async def corpo() -> servidor.Extensao:
        extensao = servidor.Extensao(porta, servidor.carregar_o_universal(), None,  # type: ignore[arg-type]
                                     tmp_path)
        await extensao.atualizar_os_controles()
        await extensao.ao_evento(_acao(acao))
        return extensao

    extensao = asyncio.run(corpo())
    tocadas = [a for a in extensao.motor.ativas if a.efeito in efeitos]
    assert {a.efeito for a in tocadas} == efeitos
    assert all(a.alvos == tuple(sorted(str(c["uniq"]) for c in QUATRO_CONTROLES)) for a in tocadas)
