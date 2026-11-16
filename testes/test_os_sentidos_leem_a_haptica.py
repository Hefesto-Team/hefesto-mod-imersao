"""O jogo que vibra pela háptica (o áudio dos motores, ``jogo.haptica``) chega ao rumble e ao golpe.

O Sackboy vibra pela háptica e não pelo motor: sem ler o ``jogo.haptica``, o rumble e o golpe ficam
calados a fase inteira. O nível dos dois caminhos soma pelo mais forte, controle a controle.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from apoio import DOIS, QUATRO, QUATRO_CONTROLES, RAIZ, TRES, UM, EscritasDeMentira
from apoio import vibracao_do_jogo as vibracao
from test_o_universal import _correr, _universal, entradas, haptica_do_jogo

import sentidos
from sentidos.golpe import Golpe
from sentidos.rumble import Rumble

Evento = tuple[str, str, "str | None", dict[str, Any]]


def _haptica(uniq: str, esq: float, dir_: float = 0.0) -> Evento:
    return haptica_do_jogo(uniq, esq, dir_)


def _motor(uniq: str, forte: int) -> Evento:
    return ("jogo.vibracao", "jogo.vibracao", uniq, vibracao(uniq, forte))


def _rodar(sentido: Any, linha: Sequence[tuple[float, Evento]], ate_ms: float,
           controles: tuple[str, ...] = (UM,)) -> list[Any]:
    fila = sorted(linha, key=lambda e: e[0])
    saida: list[Any] = []
    t = 0.0
    while t <= ate_ms:
        while fila and fila[0][0] <= t:
            topico, nome, uniq, dados = fila.pop(0)[1]
            if topico in sentido.origens:
                saida += sentido.ler(topico, nome, uniq, dados, t)
        saida += sentido.tique(t, controles, frozenset())
        t += 1000 / 60
    return saida


def _nomes(saida: list[Any], uniq: str | None = UM) -> list[str]:
    return [d.nome for d in saida if d.uniq == uniq]


def _rajada_da_haptica(uniq: str, forca: float = 0.8) -> list[tuple[float, Evento]]:
    return [(float(t), _haptica(uniq, forca, forca / 2)) for t in range(1000, 1500, 100)] + [
        (1500.0, _haptica(uniq, 0.0))]


def test_o_manifesto_pede_a_haptica_e_os_dois_sentidos_a_leem() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    assert "ler:jogo.haptica" in manifesto["permissoes"]  # (noqa-acento)
    assert "jogo.haptica" in sentidos.ORIGENS["sentido.rumble"]
    assert "jogo.haptica" in sentidos.ORIGENS["sentido.golpe"]


def test_a_haptica_longa_e_forte_e_uma_rajada_e_sobe_o_dano() -> None:
    saida = _rodar(Rumble(), _rajada_da_haptica(UM), 2000)
    assert _nomes(saida).count("rajada") == 1
    assert max(d.dados["dano_recente"] for d in saida if d.nome == "nivel") > 0.4


def test_a_haptica_curta_e_um_pulso() -> None:
    saida = _rodar(Rumble(), [(500, _haptica(UM, 0.0, 0.5)), (600, _haptica(UM, 0.0))], 1000)
    assert _nomes(saida) == ["pulso"]


def test_tres_batidas_da_haptica_no_ritmo_do_coracao_sao_um_batimento() -> None:
    linha: list[tuple[float, Evento]] = []
    for inicio in (1000, 1800, 2600):
        linha += [(inicio, _haptica(UM, 0.5)), (inicio + 100, _haptica(UM, 0.0))]
    saida = _rodar(Rumble(), linha, 3000)
    assert "batimento" in _nomes(saida)


def test_a_haptica_abaixo_do_limiar_nao_conta() -> None:
    saida = _rodar(Rumble(), _rajada_da_haptica(UM, 0.1), 2000)
    assert not _nomes(saida)


def test_o_motor_que_cala_nao_fecha_a_batida_que_a_haptica_segura() -> None:
    linha = [(t, _haptica(UM, 0.8)) for t in range(1000, 1500, 100)]
    linha += [(1000, _motor(UM, 60)), (1050, _motor(UM, 0)), (1500, _haptica(UM, 0.0))]
    saida = _rodar(Rumble(), linha, 2000)
    assert _nomes(saida) == ["rajada"]
    rajada = next(d for d in saida if d.nome == "rajada")
    assert rajada.dados["forca"] == 0.8


def test_o_motor_e_a_haptica_juntos_valem_pelo_mais_forte() -> None:
    linha = [(t, _haptica(UM, 0.3)) for t in range(1000, 1500, 100)]
    linha += [(t, _motor(UM, 230)) for t in range(1000, 1500, 100)]
    linha += [(1500, _haptica(UM, 0.0)), (1500, _motor(UM, 0))]
    saida = _rodar(Rumble(), linha, 2000)
    rajada = next(d for d in saida if d.nome == "rajada")
    assert rajada.dados["forca"] == round(230 / 255, 3)


def test_a_haptica_que_some_sem_o_zero_fecha_a_batida() -> None:
    saida = _rodar(Rumble(), [(1000, _haptica(UM, 0.8))], 3000)
    assert _nomes(saida) == ["rajada"]
    rumble = Rumble()
    _rodar(rumble, [(1000, _haptica(UM, 0.8))], 3000)
    assert rumble.batidas[UM].inicio is None


def test_a_haptica_de_um_controle_nao_vibra_o_rumble_do_outro() -> None:
    saida = _rodar(Rumble(), _rajada_da_haptica(TRES), 2000, (UM, DOIS, TRES, QUATRO))
    assert [d.uniq for d in saida if d.nome == "rajada"] == [TRES]


def test_o_ataque_seguido_da_haptica_do_jogo_e_um_golpe_dado() -> None:
    linha = [(100, entradas(UM, 200)), (200, _haptica(UM, 0.0, 0.7)), (300, _haptica(UM, 0.0))]
    saida = _rodar(Golpe(), linha, 600)
    assert [(d.nome, d.dados["gatilho"], d.dados["forca"]) for d in saida] == [("dado", "r2", 0.7)]


def test_o_golpe_nao_sobe_de_novo_quando_a_haptica_entra_com_o_motor_ja_vibrando() -> None:
    linha = [(50, _motor(UM, 200)), (100, entradas(UM, 200)), (150, _haptica(UM, 0.7)),
             (300, _haptica(UM, 0.0)), (300, _motor(UM, 0))]
    assert not _rodar(Golpe(), linha, 600)


def test_o_motor_que_parou_de_repetir_sem_o_zero_deixa_a_haptica_acertar_o_golpe() -> None:
    linha = [(50, _motor(UM, 200)), (600, entradas(UM, 200)), (650, _haptica(UM, 0.7)),
             (800, _haptica(UM, 0.0))]
    assert [d.nome for d in _rodar(Golpe(), linha, 1000)] == ["dado"]


def test_a_haptica_de_outro_controle_nao_acerta_o_golpe() -> None:
    linha = [(100, entradas(UM, 200)), (200, _haptica(DOIS, 0.7)), (300, _haptica(DOIS, 0.0))]
    assert not _rodar(Golpe(), linha, 600, (UM, DOIS))


def test_no_universal_a_haptica_do_jogo_acende_a_luz_do_dano_so_em_quem_levou() -> None:
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(_universal(QUATRO_CONTROLES), porta, 2000, _rajada_da_haptica(TRES))
    assert {p["uniq"] for _, p in porta.de("luz.set")} == {TRES}


def test_no_universal_o_ataque_com_a_haptica_do_jogo_treme_o_gatilho() -> None:
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    linha = [(100, entradas(UM, 200)), (200, _haptica(UM, 0.0, 0.7)), (300, _haptica(UM, 0.0))]
    _correr(_universal(), porta, 600, linha)
    assert [p["uniq"] for _, p in porta.de("gatilho.set")][:1] == [UM]
