"""O FAÇA do Estúdio diz a entrada pelo rótulo e pelo valor dela, nunca pelo ``$nome`` cru."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ

from estudio.blocos import Montador, blocos_da_receita, frase_do_efeito
from receita.formato import ler_receita

FABRICA = ["universal.json", "estudadas/minecraft-dungeons-ii.json"]


def _dados(arquivo: str) -> dict[str, Any]:
    dados: dict[str, Any] = json.loads((RAIZ / "receitas" / arquivo).read_text(encoding="utf-8"))
    return dados


def _dica(vista: dict[str, Any], nome: str) -> str:
    return next(str(o["dica"]) for o in vista["faca"] if o["nome"] == nome)


@pytest.mark.parametrize("arquivo", FABRICA)
def test_a_luz_do_dano_diz_a_cor_e_nenhuma_dica_leva_o_nome_cru(arquivo: str) -> None:
    vista = blocos_da_receita(_dados(arquivo))
    assert _dica(vista, "vermelho") == "pinta a luz de «Cor do dano» (#ff0000)"
    assert [o for o in vista["faca"] if "$" in o["dica"]] == []


@pytest.mark.parametrize("arquivo", FABRICA)
def test_a_cor_escolhida_vence_o_padrao_e_a_invalida_volta_a_ele(arquivo: str) -> None:
    dados = _dados(arquivo)
    escolhida = blocos_da_receita(dados, {"cor_do_dano": "#00ff00"})
    assert _dica(escolhida, "vermelho") == "pinta a luz de «Cor do dano» (#00ff00)"
    invalida = blocos_da_receita(dados, {"cor_do_dano": "vermelho"})
    assert _dica(invalida, "vermelho") == "pinta a luz de «Cor do dano» (#ff0000)"


def test_a_entrada_sem_rotulo_nem_padrao_se_diz_pelo_nome_sem_cifrao() -> None:
    frase = frase_do_efeito({"canal": "luz", "cor": "$cor_do_alarme"}, {}, {})
    assert frase == "pinta a luz de «cor do alarme»"
    assert frase_do_efeito({"canal": "mira", "ganho": 0.6}) == "pesa a mira do giroscópio até 60%"


def test_o_montador_mostra_a_cor_das_opcoes_de_agora(tmp_path: Path) -> None:
    dados = _dados("universal.json")
    opcoes: dict[str, Any] = {}
    montador = Montador(tmp_path, ler_receita, lambda: ("steam_app_1", dados), lambda: opcoes)
    assert _dica(montador.mensagem({"tipo": "blocos"}), "vermelho").endswith("(#ff0000)")
    opcoes["cor_do_dano"] = "#0000ff"
    vista = montador.mensagem({"tipo": "blocos"})
    assert _dica(vista, "vermelho") == "pinta a luz de «Cor do dano» (#0000ff)"
    assert vista["receita"]["efeitos"]["vermelho"]["cor"] == "$cor_do_dano"
