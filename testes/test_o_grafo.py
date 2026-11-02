"""O grafo é a receita vista de outro jeito, e recusa o que não fecha apontando o nó.

O ciclo, o nó a mais, o órfão e a aresta de tipo errado saem com o nó que os causa; a receita
escrita à mão vai ao grafo e volta igual. O editor de texto valida a cada tecla e só importa o
texto sem erro; a receita importada vale no tique seguinte.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ, RECEITAS

import servidor
from estudio.blocos import normalizar
from estudio.grafo import (
    TETO_DE_NOS,
    Editor,
    conferir,
    grafo_da_receita,
    receita_do_grafo,
    validar_o_texto,
)
from receita.biblioteca import Biblioteca
from receita.formato import ler_receita

JOGO = "steam_app_900000002"
RECEITAS_DE_PROVA = [
    RAIZ / "receitas" / "universal.json",
    *sorted((RAIZ / "receitas" / "estudadas").glob("*.json")),
    RECEITAS / "completa.json",
    RECEITAS / "vazia.json",
]


def _dados(arquivo: Path) -> dict[str, Any]:
    return dict(json.loads(arquivo.read_text(encoding="utf-8")))


def _erros(dados: dict[str, Any]) -> list[tuple[str, str]]:
    return [(e.no, e.frase) for e in conferir(grafo_da_receita(dados))]


def _escrita_a_mao() -> dict[str, Any]:
    return {"formato": 1, "motor": ">=1,<2", "permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
            "sentidos": {"rumble": {"de": "jogo.vibracao", "especie": "nivel",
                                    "campo": "pedido.1", "escala": [0, 255]}},
            "derivados": {"forte": {"expr": "rumble * 2"}},
            "estados": {"tremendo": {"quando": "forte > 1"}},
            "efeitos": {"tranco": {"canal": "motor", "forca": 1.0, "lado": "esquerdo"}},
            "regras": [{"quando": "tremendo", "entao": "tranco", "prioridade": 3}]}


@pytest.mark.parametrize("arquivo", RECEITAS_DE_PROVA, ids=lambda p: p.name)
def test_a_receita_vai_ao_grafo_e_volta_igual_e_sem_erro(arquivo: Path) -> None:
    dados = _dados(arquivo)
    grafo = grafo_da_receita(json.loads(json.dumps(dados)))
    assert normalizar(receita_do_grafo(grafo)) == normalizar(dados)
    assert conferir(grafo) == []


def test_a_receita_escrita_a_mao_vira_grafo_com_as_arestas_e_volta_igual() -> None:
    dados = _escrita_a_mao()
    grafo = grafo_da_receita(dados)
    assert grafo.arestas == [("sentido:rumble", "derivado:forte"),
                             ("derivado:forte", "estado:tremendo"),
                             ("estado:tremendo", "regra:0"), ("regra:0", "efeito:tranco")]
    assert conferir(grafo) == []
    volta = receita_do_grafo(grafo)
    assert normalizar(volta) == normalizar(dados)
    ler_receita(json.dumps(volta))


def test_o_ciclo_e_recusado_apontando_o_no() -> None:
    erros = _erros(_dados(RECEITAS / "ciclo.json"))
    ciclos = [e for e in erros if e[1].startswith("ciclo")]
    assert ciclos == [("derivado:medo",
                       "ciclo: derivado:medo → estado:susto → derivado:calma → derivado:medo")]


def test_sessenta_e_cinco_nos_sao_recusados_no_que_passa_do_teto() -> None:
    dados = _escrita_a_mao()
    for i in range(TETO_DE_NOS + 1 - 5):
        dados["derivados"][f"eco_{i:02d}"] = {"expr": "rumble + 0"}
    grafo = grafo_da_receita(dados)
    assert len(grafo.nos) == TETO_DE_NOS + 1
    assert grafo.nos[TETO_DE_NOS].id == "regra:0"
    assert _erros(dados) == [("regra:0", "passa de 64 nós (65)")]


def test_o_no_orfao_e_recusado_apontando_o_no() -> None:
    dados = _escrita_a_mao()
    dados["efeitos"]["sobra"] = {"canal": "luz", "cor": "#00ff00", "dura_ms": 200}
    assert _erros(dados) == [("efeito:sobra", "nó órfão: nada o lê e ele não lê nada")]


def test_a_aresta_de_tipo_errado_e_recusada_apontando_o_no() -> None:
    dados = _escrita_a_mao()
    dados["regras"].append({"quando": "rumble > 0.1", "entao": "tremendo"})
    dados["derivados"]["errado"] = {"expr": "tranco + 1"}
    erros = _erros(dados)
    assert ("regra:1", "faz «tremendo», que é estado") in erros
    assert ("derivado:errado", "lê «tranco», que é efeito") in erros
    assert not [e for e in erros if e[0] == "derivado:errado" and "órfão" in e[1]]


def test_o_texto_se_valida_com_a_linha_e_depois_com_o_no() -> None:
    assert validar_o_texto(json.dumps(_escrita_a_mao())) == []
    quebrado = validar_o_texto('{"formato": 1,\n "motor": ">=1,<2",\n "desconhecido": 3}')
    assert quebrado and all("linha" in e for e in quebrado)
    ciclo = validar_o_texto((RECEITAS / "ciclo.json").read_text(encoding="utf-8"))
    assert [(e["linha"], "ciclo" in e["frase"]) for e in ciclo] == [(10, True)]
    orfao = _escrita_a_mao()
    orfao["efeitos"]["sobra"] = {"canal": "luz", "cor": "#00ff00", "dura_ms": 200}
    assert validar_o_texto(json.dumps(orfao)) == [
        {"no": "efeito:sobra", "frase": "nó órfão: nada o lê e ele não lê nada"}]


def test_o_editor_exporta_valida_e_so_importa_o_texto_sem_erro(tmp_path: Path) -> None:
    editor = Editor(tmp_path, lambda: (JOGO, _escrita_a_mao()))
    desenho = editor.mensagem({"tipo": "grafo"})
    assert desenho["erros"] == [] and len(desenho["nos"]) == 5
    assert {n["coluna"] for n in desenho["nos"]} == {0, 1, 2, 3, 4}
    exportado = editor.mensagem({"tipo": "exportar"})
    assert exportado["nome"] == f"{JOGO}.json"
    assert json.loads(exportado["texto"]) == _escrita_a_mao()
    ciclo = (RECEITAS / "ciclo.json").read_text(encoding="utf-8")
    assert editor.mensagem({"tipo": "validar", "texto": ciclo})["erros"]
    assert editor.mensagem({"tipo": "importar", "texto": ciclo})["tipo"] == "validado"
    assert not (tmp_path / f"{JOGO}.json").exists()
    assert editor.mensagem({"tipo": "importar"})["tipo"] == "erro"
    resposta = editor.mensagem({"tipo": "importar", "texto": exportado["texto"]})
    assert resposta == {"tipo": "importado", "arquivo": f"{JOGO}.json"}
    guardada = ler_receita((tmp_path / f"{JOGO}.json").read_bytes())
    assert guardada.dados["jogo"] == {"chave": JOGO}


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"status": "ok"}


def _evento(topico: str, dados: dict[str, Any]) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": topico, "nome": topico, "uniq": None,
                                           "dados": dados}}


def test_a_receita_importada_pela_pagina_vale_na_hora(tmp_path: Path) -> None:
    porta = _Porta()
    texto = json.dumps(_escrita_a_mao())

    async def corpo() -> tuple[str, str]:
        biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                                servidor.carregar_o_universal)
        extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     biblioteca, tmp_path)
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO}))
        antes = extensao.escolhida.origem
        await extensao.ao_evento(_evento("extensao.mensagem", {
            "id": 7, "dados": {"tipo": "importar", "texto": texto}}))
        return antes, extensao.escolhida.origem

    antes, depois = asyncio.run(corpo())
    assert (antes, depois) == ("universal", "sua")
    respostas = [p["dados"]["tipo"] for m, p in porta.pedidos if m == "extensao.resposta"]
    assert respostas == ["importado"]
    assert (tmp_path / "receitas" / f"{JOGO}.json").is_file()
