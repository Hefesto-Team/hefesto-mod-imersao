"""Os blocos QUANDO e FAÇA são a receita vista de outro jeito, e a linha do tempo toca sem o jogo.

A ida e a volta (receita → blocos → receita) sai igual byte a byte depois de normalizada, também
passando pelo JSON da página. Uma linha gravada, tocada com duas receitas diferentes, dá os efeitos
de cada uma; o microfone nunca entra na gravação.
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ, RECEITAS, UM, vibracao_do_jogo

import servidor
from estudio.blocos import (
    Montador,
    blocos_da_receita,
    frase_do_efeito,
    normalizar,
    receita_dos_blocos,
)
from estudio.linha_do_tempo import (
    DURACAO_MS,
    Gravador,
    LinhaDoTempo,
    Marco,
    efeitos_da_linha,
    gravar_no_disco,
    ler_do_disco,
)
from receita.formato import ler_receita

JOGO = "steam_app_900000001"
RECEITAS_DE_PROVA = [
    RAIZ / "receitas" / "universal.json",
    *sorted((RAIZ / "receitas" / "estudadas").glob("*.json")),
    RECEITAS / "completa.json",
    RECEITAS / "vazia.json",
]


def _dados(arquivo: Path) -> dict[str, Any]:
    return dict(json.loads(arquivo.read_text(encoding="utf-8")))


@pytest.mark.parametrize("arquivo", RECEITAS_DE_PROVA, ids=lambda p: p.name)
def test_a_receita_vai_aos_blocos_e_volta_igual_byte_a_byte(arquivo: Path) -> None:
    dados = _dados(arquivo)
    vista = json.loads(json.dumps(blocos_da_receita(dados)))
    volta = receita_dos_blocos(vista)
    assert normalizar(volta) == normalizar(dados)
    ler_receita(json.dumps(volta))


def test_a_regra_escrita_a_mao_com_todos_os_campos_volta_inteira() -> None:
    regra = {"quando": "a > 0.5", "entao": "x", "senao": ["y", "z"], "prioridade": 7,
             "espera_ms": 900, "para": ["p1", "p3"]}
    volta = receita_dos_blocos(blocos_da_receita({"formato": 1, "regras": [regra]}))
    assert volta["regras"] == [regra]


def test_os_blocos_listam_o_quando_e_o_faca_com_a_frase_de_cada_efeito() -> None:
    dados = _dados(RAIZ / "receitas" / "universal.json")
    vista = blocos_da_receita(dados)
    assert [q["nome"] for q in vista["quando"]] == [
        *dados["estados"], *dados["derivados"], *dados["sentidos"]]
    dicas = {f["nome"]: f["dica"] for f in vista["faca"]}
    assert dicas and all(dicas.values())
    assert frase_do_efeito({"canal": "motor", "forca": 0.6, "lado": "esquerdo"}) == (
        "vibra o motor da esquerda a 60%")


def _receita_do_motor() -> dict[str, Any]:
    return {"formato": 1, "motor": ">=1,<2", "permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
            "sentidos": {"rumble": {"de": "jogo.vibracao", "especie": "nivel",
                                    "campo": "efetivo.1", "escala": [0, 255]}},
            "efeitos": {"tranco": {"canal": "motor", "forca": 1.0, "lado": "esquerdo"}},
            "regras": [{"quando": "rumble > 0.5", "entao": "tranco"}]}


def _receita_da_luz() -> dict[str, Any]:
    return {"formato": 1, "motor": ">=1,<2", "permissoes": ["ler:jogo.som"],  # (noqa-acento)
            "sentidos": {"estalo": {"de": "jogo.som", "especie": "evento"}},
            "efeitos": {"vermelho": {"canal": "luz", "cor": "#ff0000", "dura_ms": 400}},
            "regras": [{"quando": "estalo", "entao": "vermelho"}]}


def _som(t_s: float) -> dict[str, Any]:
    return {"t": t_s, "evento": "estalo", "lado": "centro", "energia": 0.5, "canais": 2,
            "bandas": [0.1] * 24, "amostras": "não se grava"}


def _gravada() -> LinhaDoTempo:
    gravador = Gravador()
    gravador.ouvir("jogo.vibracao", "jogo.vibracao", UM, vibracao_do_jogo(UM, 200), 0.0)
    gravador.gravar(1000.0)
    eventos: list[tuple[float, str, str | None, dict[str, Any]]] = [
        (1500.0, "jogo.vibracao", UM, vibracao_do_jogo(UM, 220)),
        (1800.0, "jogo.vibracao", UM, vibracao_do_jogo(UM, 0)),
        (2500.0, "microfone.nivel", UM, {"uniq": UM, "nivel": 0.9, "mudo": False, "t": 1.5}),
        (3000.0, "jogo.som", None, _som(2.0)),
        (4000.0, "jogo.vibracao", UM, vibracao_do_jogo(UM, 230)),
        (4300.0, "jogo.vibracao", UM, vibracao_do_jogo(UM, 0)),
    ]
    for t, topico, uniq, dados in eventos:
        gravador.ouvir(topico, topico, uniq, dados, t)
    return gravador.parar()


def test_o_gravador_guarda_so_os_sinais_e_nunca_o_microfone() -> None:
    linha = _gravada()
    assert [m.topico for m in linha.marcos] == [
        "jogo.vibracao", "jogo.vibracao", "jogo.som", "jogo.vibracao", "jogo.vibracao"]
    assert [m.t_ms for m in linha.marcos] == [500.0, 800.0, 2000.0, 3000.0, 3300.0]
    assert "amostras" not in linha.marcos[2].dados
    assert linha.marcos[2].dados["bandas"] == [0.1] * 24


def test_o_gravador_para_sozinho_nos_cinco_minutos() -> None:
    gravador = Gravador()
    gravador.gravar(0.0)
    gravador.ouvir("jogo.som", "jogo.som", None, _som(1.0), DURACAO_MS - 1)
    gravador.ouvir("jogo.som", "jogo.som", None, _som(2.0), DURACAO_MS + 1)
    assert not gravador.gravando and len(gravador.linha.marcos) == 1


def test_a_mesma_linha_com_duas_receitas_da_os_efeitos_de_cada_uma() -> None:
    linha = _gravada()
    controles = [{"uniq": UM, "jogador": 1}]
    do_motor = efeitos_da_linha(linha, ler_receita(json.dumps(_receita_do_motor())), controles)
    da_luz = efeitos_da_linha(linha, ler_receita(json.dumps(_receita_da_luz())), controles)
    assert [(e[2], e[4]) for e in do_motor] == [("motor", "tranco"), ("motor", "tranco")]
    assert 500 <= do_motor[0][0] < 520 and 3000 <= do_motor[1][0] < 3020
    assert [(e[2], e[4]) for e in da_luz] == [("luz", "vermelho")]
    assert 2000 <= da_luz[0][0] < 2020


def test_ajustar_o_bloco_e_tocar_de_novo_muda_o_que_sai() -> None:
    linha = _gravada()
    vista = blocos_da_receita(_receita_do_motor())
    vista["blocos"][0]["quando"] = "rumble > 0.88"
    ajustada = ler_receita(json.dumps(receita_dos_blocos(vista)))
    saida = efeitos_da_linha(linha, ajustada, [{"uniq": UM, "jogador": 1}])
    assert [round(e[0]) // 100 for e in saida] == [30]


def test_a_linha_vai_ao_disco_e_volta(tmp_path: Path) -> None:
    linha = _gravada()
    gravar_no_disco(tmp_path, JOGO, linha)
    assert ler_do_disco(tmp_path, JOGO) == linha
    assert ler_do_disco(tmp_path, "steam_app_1") is None
    with pytest.raises(ValueError):
        LinhaDoTempo.de_json(b'{"formato": 1, "marcos": [[0, "microfone.nivel", "x", null, {}]]}')
    assert Marco.de_json([1, "jogo.som", "jogo.som", None, {}]).uniq is None


def test_o_montador_grava_so_a_receita_que_valida(tmp_path: Path) -> None:
    receita = _receita_do_motor()
    montador = Montador(tmp_path, ler_receita, lambda: (JOGO, receita))
    vista = montador.mensagem({"tipo": "blocos"})
    assert vista["jogo"] == JOGO and vista["blocos"][0]["faca"] == ["tranco"]
    torta = copy.deepcopy(vista)
    torta["blocos"][0]["faca"] = ["nao_existe"]
    assert montador.mensagem({"tipo": "montar", "vista": torta})["tipo"] == "erro"
    assert not (tmp_path / f"{JOGO}.json").exists()
    vista["blocos"][0]["prioridade"] = 9
    assert montador.mensagem({"tipo": "montar", "vista": vista}) == {
        "tipo": "montado", "arquivo": f"{JOGO}.json"}
    guardada = ler_receita((tmp_path / f"{JOGO}.json").read_bytes())
    assert guardada.regras[0]["prioridade"] == 9
    assert guardada.dados["jogo"] == {"chave": JOGO}


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"status": "ok"}


def _evento(topico: str, dados: dict[str, Any], uniq: str | None = None) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": topico, "nome": topico, "uniq": uniq,
                                           "dados": dados}}


def test_a_pagina_grava_para_e_toca_a_linha_no_motor_vivo(tmp_path: Path) -> None:
    porta = _Porta()

    async def corpo() -> list[Any]:
        extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     None, tmp_path)
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO}))
        for tipo in ("gravar",):
            await extensao.ao_evento(_evento("extensao.mensagem", {"id": 1, "dados": {"tipo": tipo}}))
        await extensao.ao_evento(_evento("jogo.vibracao", vibracao_do_jogo(UM, 220), UM))
        await extensao.ao_evento(_evento("microfone.nivel", {"uniq": UM, "nivel": 0.5}, UM))
        await extensao.ao_evento(_evento("extensao.mensagem", {"id": 2, "dados": {"tipo": "parar"}}))
        vistos: list[Any] = []
        extensao.motor.evento = lambda *a: vistos.append(a)  # type: ignore[method-assign]
        await extensao.ao_evento(_evento("extensao.mensagem", {"id": 3, "dados": {"tipo": "tocar"}}))
        assert extensao.tocando is not None
        await asyncio.wait_for(extensao.tocando, 2)
        return vistos

    vistos = asyncio.run(corpo())
    respostas = [p["dados"] for m, p in porta.pedidos if m == "extensao.resposta"]
    assert [r["tipo"] for r in respostas] == ["gravando", "gravado", "tocando", "tocado"]
    assert respostas[1]["marcos"] == 1
    assert [v[0] for v in vistos if v[0] != "extensao.mensagem"] == ["jogo.vibracao"]
    assert ler_do_disco(tmp_path, JOGO) is not None
    assert ("eventos.assinar", {"topicos": ["jogo.som"]}) in porta.pedidos
