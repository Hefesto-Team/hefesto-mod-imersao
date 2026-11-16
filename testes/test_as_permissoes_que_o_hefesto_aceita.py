"""O manifesto pede o que as receitas usam e o Hefesto aceita, e a porta os assina."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ, UM, EscritasDeMentira, PortaDeMentira, ate
from test_o_universal import _correr, _universal, microfone, na_mao, som

import servidor
from receita.formato import ler_receita


def _manifesto() -> dict[str, Any]:
    dado: dict[str, Any] = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    return dado


def _receitas() -> list[Path]:
    return [RAIZ / "receitas" / "universal.json",
            *sorted((RAIZ / "receitas" / "estudadas").glob("*.json"))]


def _o_que_se_le() -> set[str]:
    lidos: set[str] = set()
    for arquivo in _receitas():
        receita = ler_receita(arquivo.read_bytes())
        lidos |= servidor._lidos(receita) | servidor.topicos_do_caminho(receita)
        lidos |= {p.removeprefix("ler:") for p in receita.dados.get("permissoes", [])}  # (noqa-acento)
    return lidos


def _canais_escritos() -> set[str]:
    canais: set[str] = set()
    for arquivo in _receitas():
        canais |= {e["canal"] for e in ler_receita(arquivo.read_bytes()).secao("efeitos").values()}
    return {"vibracao" if c == "motor" else c for c in canais}


def test_todo_topico_que_a_receita_le_esta_no_manifesto_e_na_porta() -> None:
    permissoes = set(_manifesto()["permissoes"])  # (noqa-acento)
    lidos = _o_que_se_le()
    assert {"jogo.som", "microfone.nivel", "jogo.tela", "jogo.identidade"} <= lidos
    assert sorted(t for t in lidos if f"ler:{t}" not in permissoes) == []
    assert sorted(t for t in lidos if t not in servidor.TOPICOS_DA_PORTA) == []


def test_todo_canal_que_a_receita_escreve_esta_no_manifesto() -> None:
    permissoes = set(_manifesto()["permissoes"])  # (noqa-acento)
    canais = _canais_escritos()
    assert {"haptica", "som", "leds"} <= canais
    assert sorted(c for c in canais if f"escrever:{c}" not in permissoes) == []


def test_o_manifesto_passa_pelo_validador_do_hefesto_com_cada_permissao_conhecida() -> None:
    do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto")
    manifesto = do_hefesto.ler_manifesto(RAIZ)
    assert all(do_hefesto.permissao_valida(p) for p in manifesto.permissoes)
    for topico in servidor.TOPICOS_DA_PORTA:
        assert topico in do_hefesto.TOPICOS_DE_LEITURA


def test_o_coracao_e_o_susto_tocam_a_partir_do_jogo_som() -> None:
    linha = [(t, microfone(UM, 0.01)) for t in range(0, 20_000, 500)] + na_mao(UM, 20_000)
    linha += [(18_000, som("direito", 0.45, 1234.5))]
    motor, porta = _universal(), EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(motor, porta, 19_000, linha)
    padroes = {p["id"] for _, p in porta.de("haptica.tocar")}  # (noqa-acento)
    assert {"coracao", "susto"} <= padroes
    assert [p["som"] for _, p in porta.de("som.tocar")] == ["recorte"]


class _PortaQueToca(PortaDeMentira):
    async def atender(self, leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        self.escritores.append(escritor)
        while linha := await leitor.readline():
            pedido = json.loads(linha)
            metodo, params = pedido["method"], pedido.get("params") or {}
            self.pedidos.append((metodo, params))
            resultado: Any = {"status": "ok"}
            if metodo == "controles.lista":
                resultado = {"controles": self.controles}
            elif metodo == "eventos.assinar":
                self.assinados |= set(params.get("topicos", []))
            elif metodo == "eventos.desassinar":
                self.assinados -= set(params.get("topicos", []))
            escritor.write(json.dumps({"jsonrpc": "2.0", "id": pedido["id"],
                                       "result": resultado}).encode() + b"\n")
            await escritor.drain()


@pytest.fixture
def pasta_curta() -> Iterator[Path]:
    pasta = Path(tempfile.mkdtemp(prefix="imp-"))
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def test_a_porta_assina_o_jogo_som_e_o_estalo_vibra_o_lado_e_a_tela_espera_o_clique(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = _PortaQueToca()
    dados = pasta_curta / "dados"
    dados.mkdir()
    monkeypatch.setenv("HEFESTO_MOD_SOCKET", str(pasta_curta / "mods.sock"))
    monkeypatch.setenv("HEFESTO_MOD_FICHA", "ficha-de-mentira")
    monkeypatch.setenv("HEFESTO_MOD_DADOS", str(dados))

    async def corpo(extensao: servidor.Extensao) -> None:
        assert {"jogo.som", "microfone.nivel"} <= porta.assinados
        assert "jogo.tela" not in porta.assinados
        await porta.publicar("jogo.som", "jogo.som", {
            "t": 1.0, "evento": "estalo", "lado": "esquerdo", "energia": 0.4, "canais": 2,
            "bandas": [0.0] * 24})
        await ate(lambda: any(p["forte"] for p in porta.de("vibracao.set")))
        (dados / servidor.ARQUIVO_DAS_OPCOES).write_text('{"sentido_tela": true}')
        await asyncio.sleep(3 * servidor.RELE_AS_OPCOES_S)
        assert "jogo.tela" not in porta.assinados and not porta.de("tela.ver")
        await extensao.ao_evento({"method": "evento", "params": {
            "topico": "extensao.acao", "dados": {"acao": "ver_a_tela"}}})
        await ate(lambda: "jogo.tela" in porta.assinados)
        await extensao.ao_evento({"method": "evento", "params": {
            "topico": "extensao.acao", "dados": {"acao": "parar_de_ver"}}})
        await ate(lambda: "jogo.tela" not in porta.assinados)
        assert porta.metodos.count("tela.ver") == porta.metodos.count("tela.parar") == 1

    async def rodar() -> int:
        socket = await asyncio.start_unix_server(porta.atender, path=str(pasta_curta / "mods.sock"))
        extensoes: list[servidor.Extensao] = []
        processo = asyncio.create_task(servidor.rodar(extensoes.append))
        try:
            await ate(lambda: bool(extensoes))
            await corpo(extensoes[0])
            for escritor in porta.escritores:
                escritor.close()
            return await asyncio.wait_for(processo, 5)
        finally:
            socket.close()

    assert asyncio.run(rodar()) == 0
    assert {"topicos": ["jogo.tela"]} in porta.de("eventos.desassinar")


def test_a_extensao_que_sai_vendo_a_tela_manda_o_tela_parar(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = _PortaQueToca()
    dados = pasta_curta / "dados"
    dados.mkdir()
    monkeypatch.setenv("HEFESTO_MOD_SOCKET", str(pasta_curta / "mods.sock"))
    monkeypatch.setenv("HEFESTO_MOD_FICHA", "ficha-de-mentira")
    monkeypatch.setenv("HEFESTO_MOD_DADOS", str(dados))

    async def rodar() -> int:
        socket = await asyncio.start_unix_server(porta.atender, path=str(pasta_curta / "mods.sock"))
        extensoes: list[servidor.Extensao] = []
        processo = asyncio.create_task(servidor.rodar(extensoes.append))
        try:
            await ate(lambda: bool(extensoes))
            extensao = extensoes[0]
            await extensao.ao_evento({"method": "evento", "params": {
                "topico": "extensao.acao", "dados": {"acao": "ver_a_tela"}}})
            await ate(lambda: "jogo.tela" in porta.assinados)
            assert "tela.parar" not in porta.metodos
            await extensao.porta.eventos.put({"method": "porta.fechou"})
            codigo = await asyncio.wait_for(processo, 5)
            for escritor in porta.escritores:
                escritor.close()
            return codigo
        finally:
            socket.close()

    assert asyncio.run(rodar()) == 0
    assert porta.metodos.count("tela.ver") == porta.metodos.count("tela.parar") == 1
