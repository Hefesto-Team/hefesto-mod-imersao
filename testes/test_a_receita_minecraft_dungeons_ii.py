"""A receita estudada do Minecraft Dungeons II (Steam 1912410) numa linha do tempo gravada.

O jogo manda no controle (21 efeitos de gatilho adaptativo nos arquivos dele) e a receita só soma:
o coração pelo batimento do rumble, o susto pelo estalo forte na cena tensa e o lado pelo som. Em
cada canal vale o mais forte: o gatilho do jogo sai igual enquanto é o mais forte, e o impacto da
receita só entra onde passa dele.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from apoio import RAIZ, UM, EscritasDeMentira
from test_o_universal import (
    Evento,
    TatoVivoDeMentira,
    _correr,
    _motores,
    entradas,
    gatilho_do_jogo,
    rumble,
    som,
)

import servidor
from motor.laco import Motor
from receita.biblioteca import Biblioteca
from receita.formato import Receita, ler_receita

ARQUIVO = RAIZ / "receitas" / "estudadas" / "minecraft-dungeons-ii.json"
CHAVE = "steam_app_1912410"


def _receita() -> Receita:
    return ler_receita(ARQUIVO.read_bytes())


def _motor(opcoes: dict[str, Any] | None = None) -> Motor:
    motor = Motor(_receita(), opcoes)
    motor.controles([{"uniq": UM, "jogador": 1}])
    return motor


def _golpe_no_r2(t: float) -> list[tuple[float, Evento]]:
    return [(t, entradas(UM, 200)), (t + 80, rumble(UM, 180)), (t + 200, rumble(UM, 0)),
            (t + 300, entradas(UM, 0))]


def _batimento(de_ms: int, ate_ms: int) -> list[tuple[float, Evento]]:
    linha: list[tuple[float, Evento]] = []
    for t in range(de_ms, ate_ms, 800):
        linha += [(t, rumble(UM, 120)), (t + 80, rumble(UM, 0))]
    return linha


LINHA_DO_GATILHO: list[tuple[float, Evento]] = [
    (500, gatilho_do_jogo(UM, "direito", "arma", 0.9)),
    *_golpe_no_r2(1000),
    (2000, gatilho_do_jogo(UM, "direito", "arma", 0.3)),
    *_golpe_no_r2(2500),
    (3500, gatilho_do_jogo(UM, "direito", "arma", 1.0)),
    *_golpe_no_r2(4000),
]


def test_a_receita_e_do_jogo_comeca_sem_memoria_e_a_biblioteca_a_escolhe(tmp_path: Path) -> None:
    receita = _receita()
    assert receita.dados["jogo"] == {"chave": CHAVE, "leitura_de_memoria": "nao"}  # (noqa-acento)
    assert not [p for p in receita.secao("permissoes") if "memoria" in p]  # (noqa-acento)
    biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                            servidor.carregar_o_universal)
    escolhida = biblioteca.para(CHAVE)
    assert (escolhida.origem, escolhida.arquivo) == ("estudada", ARQUIVO)
    assert biblioteca.para("steam_app_1").origem == "universal"


def test_o_gatilho_do_jogo_sai_igual_enquanto_e_o_mais_forte_e_o_impacto_entra_onde_passa() -> None:
    porta = TatoVivoDeMentira()
    _correr(_motor(), porta, 5000, LINHA_DO_GATILHO)
    gatilhos = [(round(t), p["lado"], p["modo"]) for t, p in porta.de("gatilho.set")]
    impactos = [g for g in gatilhos if g[2] == "Vibration"]
    assert [g[1:] for g in impactos] == [("direito", "Vibration")]
    assert 2580 <= impactos[0][0] <= 2600
    assert not [g for g in gatilhos if 500 < g[0] < 2000 and g[2] != "Off"]
    assert not [g for g in gatilhos if g[0] > 3500]
    assert not porta.recusas


def test_o_motor_do_jogo_mais_forte_cala_o_lado_e_o_mais_fraco_o_deixa_sair() -> None:
    linha: list[tuple[float, Evento]] = [(t, rumble(UM, 255, 255)) for t in range(0, 1500, 250)]
    linha += [(1500, rumble(UM, 0, 0)), (600, som("esquerdo", 0.4, 0.6))]
    linha += [(t, rumble(UM, 40, 40)) for t in range(2000, 3500, 250)]
    linha += [(3500, rumble(UM, 0, 0)), (2600, som("direito", 0.4, 2.6))]
    porta = EscritasDeMentira()
    _correr(_motor(), porta, 4000, linha)
    motores = _motores(porta)
    assert not [m for m in motores if 600 <= m[0] < 1000 and (m[1] or m[2])]
    assert [m for m in motores if 2600 <= m[0] < 2800 and m[2] == round(0.6 * 255)]


def test_o_estalo_da_esquerda_vibra_a_esquerda_e_o_lado_na_luz_acende_as_luzes_do_lado() -> None:
    porta = EscritasDeMentira()
    _correr(_motor({"lado_na_luz": True}), porta, 1500,
            [(200, som("esquerdo", 0.4, 0.2)), (900, som("direito", 0.4, 0.9))])
    motores = _motores(porta)
    assert [m for m in motores if 200 <= m[0] < 400 and m[1] == round(0.6 * 255) and not m[2]]
    assert [m for m in motores if 900 <= m[0] < 1100 and m[2] == round(0.6 * 255) and not m[1]]
    assert [p["mascara"] for _, p in porta.de("leds.set")] == [0b00011, 0b11000]


def test_o_batimento_do_rumble_liga_o_coracao_e_o_estalo_forte_na_cena_tensa_e_o_susto() -> None:
    linha = _batimento(0, 9000) + [(7000, som("direito", 0.45, 70.0))]
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(_motor(), porta, 9000, linha)
    coracao = [(t, p) for t, p in porta.de("haptica.tocar")
               if p["id"] == "coracao" and p["forca"] > 0]  # (noqa-acento)
    assert coracao and coracao[0][0] < 6000
    assert {(p["forca"], p["bpm"]) for _, p in coracao} <= {(0.5, 95), (0.75, 130)}  # (noqa-acento)
    assert len([t for t, _ in porta.de("haptica.tocar") if 6000 <= t < 7000]) < 6
    assert [p for _, p in porta.de("som.tocar")] == [
        {"uniq": UM, "som": "recorte", "volume": 1.0, "t": 70.0, "dura_s": 0.3}]
    assert [round(t) for t, p in porta.de("haptica.tocar") if p["id"] == "susto"][:1] == [7000]  # (noqa-acento)


def test_sem_tensao_o_estalo_forte_nao_assusta() -> None:
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(_motor(), porta, 3000, [(1000, som("direito", 0.45, 1.0))])
    assert not porta.de("som.tocar")
    assert not [p for _, p in porta.de("haptica.tocar") if p["forca"] > 0]  # (noqa-acento)
