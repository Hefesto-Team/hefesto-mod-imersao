"""A receita que lê memória ou tela assina na língua da porta do Hefesto.

A porta pede ``memoria: {entradas, faixa}`` para o ``jogo.memoria`` e ``tela: {regioes}`` para o
``jogo.tela``, nas formas dela (``cadeia_de_ponteiros``, ``largura``/``altura``, ``cor``). A porta de
mentira daqui confere cada assinatura e cada ``tela.ver`` com as funções do próprio Hefesto, sem
dublê, e recusa o tópico que ele não conhece e o que o manifesto não pede.
"""
from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ

import servidor
from receita import formato
from receita.biblioteca import Biblioteca
from receita.formato import ReceitaRecusada, ler_receita

porta_do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.porta")

MANIFESTO = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
PERMISSOES = set(MANIFESTO["permissoes"])  # (noqa-acento)
LEITURA = {"tipo": "f32", "modulo": "Jogo-Win64-Shipping.exe", "base": "0x04A1C2D0",  # (noqa-acento)
           "saltos": ["0x30", "0x2A8"], "hz": 10}
REGIAO = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.05, "cor": [200, 30, 30], "tolerancia": 40}
RECEITA: dict[str, Any] = {
    "formato": 1, "motor": ">=1,<2",
    "jogo": {"chave": "steam_app_1234567", "janela": ["Jogo-Win64-Shipping.exe"],
             "builds": {"steam_buildid": ["1000", "2000"]}, "leitura_de_memoria": "pede"},
    "permissoes": ["ler:jogo.memoria", "ler:jogo.tela", "ler:botoes"],  # (noqa-acento)
    "sentidos": {
        "vida": {"de": "jogo.memoria", "especie": "nivel", "escala": [0, 100], "leitura": LEITURA},
        "barra": {"de": "jogo.tela", "especie": "nivel", "regiao": REGIAO},
        "cruz": {"de": "botoes", "especie": "evento"}},
}


class PortaQueConfere:
    """O ``eventos.assinar`` e o ``tela.ver`` conferidos como o Hefesto os confere."""

    def __init__(self, recusa: str | None = None) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []
        self.assinados: list[str] = []
        self.recusa = recusa

    def _confere(self, topicos: list[str], params: dict[str, Any]) -> None:
        for topico in topicos:
            if topico not in porta_do_hefesto.TOPICOS_DE_LEITURA:
                raise porta_do_hefesto.RecusaError(-32602, f"tópico desconhecido: {topico}")
            if f"ler:{topico}" not in PERMISSOES:
                raise porta_do_hefesto.RecusaError(-32010, f"falta a permissão ler:{topico}")
        if self.recusa in topicos:
            raise porta_do_hefesto.RecusaError(-32003, "recusa forçada")
        if "jogo.memoria" in topicos:
            porta_do_hefesto._pedido_da_memoria(params)
        if "jogo.tela" in topicos:
            porta_do_hefesto._regioes_do_pedido(params)

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        try:
            if metodo == "eventos.assinar":
                self._confere(params["topicos"], params)
            elif metodo == "tela.ver":
                porta_do_hefesto._regioes_do_pedido(params)
        except porta_do_hefesto.RecusaError as exc:
            raise servidor.RecusaDaPorta(exc.frase, exc.codigo, exc.dados) from exc
        if metodo == "eventos.assinar":
            self.assinados += params["topicos"]
        elif metodo == "eventos.desassinar":
            self.assinados = [t for t in self.assinados if t not in params["topicos"]]
        return {"controles": []} if metodo == "controles.lista" else {}

    def de(self, metodo: str) -> list[dict[str, Any]]:
        return [p for m, p in self.pedidos if m == metodo]


def _extensao(porta: PortaQueConfere, dados: dict[str, Any] | None = None
              ) -> servidor.Extensao:
    receita = ler_receita(json.dumps(dados or RECEITA))
    return servidor.Extensao(porta, receita)  # type: ignore[arg-type]


def test_a_memoria_e_a_regiao_se_assinam_com_o_que_a_porta_confere() -> None:
    """D-2511-A-RECEITA-DE-MEMORIA-E-TELA-ASSINA-NA-LINGUA-DA-PORTA: a leitura e a região vão à porta."""
    porta = PortaQueConfere()
    extensao = _extensao(porta)

    async def corpo() -> None:
        await extensao.assinar()
        await extensao.ver_a_tela()

    asyncio.run(corpo())
    assert {"jogo.memoria", "jogo.tela", "botoes"} <= set(porta.assinados)
    memoria = next(p for p in porta.de("eventos.assinar") if "jogo.memoria" in p["topicos"])
    assert memoria["topicos"] == ["jogo.memoria"]
    assert memoria["memoria"] == {
        "entradas": [{"nome": "vida", "modulo": "Jogo-Win64-Shipping.exe", "tipo": "f32",  # (noqa-acento)
                      "cadeia_de_ponteiros": [0x04A1C2D0, 0x30, 0x2A8], "hz": 10}],
        "faixa": {"min": 1000, "max": 2000}}
    regioes = {"regioes": [{"nome": "barra", "x": 0.1, "y": 0.2, "largura": 0.3, "altura": 0.05,
                            "cor": [200, 30, 30], "tolerancia": 40}]}
    assert porta.de("tela.ver") == [{"tela": regioes}]
    assert next(p for p in porta.de("eventos.assinar") if "jogo.tela" in p["topicos"]) == {
        "topicos": ["jogo.tela"], "tela": regioes}


@pytest.mark.parametrize("arquivo", sorted(RAIZ.glob("receitas/**/*.json")),
                         ids=lambda a: a.name)
def test_a_receita_de_fabrica_assina_e_ve_a_tela_sem_recusa(arquivo: Any) -> None:
    porta = PortaQueConfere()
    extensao = _extensao(porta, json.loads(arquivo.read_text(encoding="utf-8")))

    async def corpo() -> None:
        await extensao.assinar()
        await extensao.ver_a_tela()

    asyncio.run(corpo())
    assert extensao.vendo
    assert not extensao._recusas_ditas


def test_a_assinatura_recusada_vai_ao_diario_uma_vez_e_os_outros_topicos_ficam_assinados(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueConfere(recusa="jogo.memoria")
    extensao = _extensao(porta)

    async def corpo() -> None:
        await extensao.assinar()
        await extensao.assinar()

    asyncio.run(corpo())
    assert "botoes" in porta.assinados and "jogo.memoria" not in porta.assinados
    diario = capsys.readouterr().err
    assert diario.count("recusou a assinatura de jogo.memoria: recusa forçada") == 1


def test_a_recusa_se_diz_de_novo_quando_a_receita_volta_a_valer(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "receitas").mkdir()
    (tmp_path / "receitas" / "jogo.json").write_text(json.dumps(RECEITA), encoding="utf-8")
    porta = PortaQueConfere(recusa="jogo.memoria")
    biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path, servidor.carregar_o_universal)
    extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                 biblioteca, tmp_path)

    async def corpo() -> None:
        for jogo in (RECEITA["jogo"]["chave"], None, RECEITA["jogo"]["chave"]):
            extensao.jogo = jogo
            await extensao.escolher()

    asyncio.run(corpo())
    assert capsys.readouterr().err.count("recusou a assinatura de jogo.memoria: recusa forçada") == 2

def test_a_memoria_que_muda_com_a_receita_se_assina_de_novo_com_a_leitura_nova() -> None:
    porta = PortaQueConfere()
    extensao = _extensao(porta)
    outra = copy.deepcopy(RECEITA)
    outra["sentidos"]["vida"]["leitura"]["base"] = "0x1000"

    async def corpo() -> None:
        await extensao.assinar()
        extensao.receita = ler_receita(json.dumps(outra))
        await extensao.assinar()

    asyncio.run(corpo())
    entradas = [p["memoria"]["entradas"][0]["cadeia_de_ponteiros"][0]
                for p in porta.de("eventos.assinar") if "jogo.memoria" in p["topicos"]]
    assert entradas == [0x04A1C2D0, 0x1000]
    assert porta.de("eventos.desassinar") == [{"topicos": ["jogo.memoria"]}]
    assert porta.assinados.count("jogo.memoria") == 1


def test_todo_topico_que_o_formato_aceita_a_porta_entrega_e_o_manifesto_pede() -> None:
    topicos = set(formato.TOPICOS)
    assert topicos <= set(servidor.TOPICOS_DA_PORTA)
    assert topicos <= set(porta_do_hefesto.TOPICOS_DE_LEITURA)
    assert {f"ler:{t}" for t in topicos} <= PERMISSOES


def test_a_receita_que_le_a_bateria_se_recusa_com_a_linha() -> None:
    dados = {"formato": 1, "motor": ">=1,<2", "permissoes": ["ler:bateria"],  # (noqa-acento)
             "sentidos": {"carga": {"de": "bateria", "especie": "nivel", "campo": "nivel"}}}
    with pytest.raises(ReceitaRecusada, match="sentidos.carga.de: «bateria» fora da lista"):
        ler_receita(json.dumps(dados))


@pytest.mark.parametrize("campo, valor, frase", [
    ("regiao.cor", None, "sentidos.barra.regiao: falta o campo «cor»"),
    ("regiao.cor", [300, 0, 0], "sentidos.barra.regiao.cor.0: 300 fora da faixa"),
    ("leitura.hz", 31, "sentidos.vida.leitura.hz: 31 fora da faixa"),
    ("leitura.saltos", ["0x1"] * 8, "sentidos.vida.leitura.saltos: pede de 0 a 7 itens, e tem 8"),
])
def test_o_formato_recusa_com_a_linha_o_que_a_porta_recusaria(
        campo: str, valor: Any, frase: str) -> None:
    dados = copy.deepcopy(RECEITA)
    onde, chave = campo.split(".")
    sentido = dados["sentidos"]["barra" if onde == "regiao" else "vida"][onde]
    if valor is None:
        del sentido[chave]
    else:
        sentido[chave] = valor
    with pytest.raises(ReceitaRecusada) as recusa:
        ler_receita(json.dumps(dados, indent=1))
    assert frase in str(recusa.value)
