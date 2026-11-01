"""O esqueleto da extensão: o manifesto pelo validador do Hefesto, a licença e o processo inteiro
falando com a porta de mentira num socket."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ, RECEITAS, UM, PortaDeMentira, ate, vibracao_do_jogo

import servidor

ABAS_DO_MODO = {"02", "03", "04", "05", "10"}


def _bruto() -> dict[str, Any]:
    dado: dict[str, Any] = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    return dado


def test_o_manifesto_vale_no_hefesto_e_o_modo_da_aba_espera_o_hefesto_que_o_conhece() -> None:
    do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto")
    bruto = _bruto()
    if "modos_de_aba" in do_hefesto.Manifesto.model_fields:
        manifesto = do_hefesto.ler_manifesto(RAIZ)
    else:
        with pytest.raises(do_hefesto.ManifestoRecusadoError, match="modos_de_aba"):
            do_hefesto.ler_manifesto(RAIZ)
        bruto.pop("modos_de_aba")
        manifesto = do_hefesto.Manifesto.model_validate(bruto)
    assert manifesto.id == "imersao" and manifesto.api == ">=2,<3"
    assert manifesto.licenca == "GPL-3.0-or-later"
    assert do_hefesto.aceita_a_api(manifesto.api)
    assert "rede:nenhuma" in manifesto.permissoes
    assert not [p for p in manifesto.permissoes if p.startswith("publicar:")]


def test_o_modo_da_aba_tem_a_forma_da_sprint_do_hefesto() -> None:
    modos = _bruto()["modos_de_aba"]
    assert len(modos) == 1
    modo = modos[0]
    assert set(modo) == {"id", "rotulo", "dica", "abas"}
    assert modo["rotulo"] == "Modo imersão" and len(modo["rotulo"]) <= 20
    assert len(modo["dica"]) <= 120
    assert set(modo["abas"]) == ABAS_DO_MODO


def test_a_licenca_e_a_gpl_3_inteira_e_o_pyproject_declara_o_spdx() -> None:
    texto = (RAIZ / "LICENSE").read_text(encoding="utf-8")
    assert texto.lstrip().startswith("GNU GENERAL PUBLIC LICENSE")
    assert "Version 3, 29 June 2007" in texto and "END OF TERMS AND CONDITIONS" in texto
    assert 'license = "GPL-3.0-or-later"' in (RAIZ / "pyproject.toml").read_text(encoding="utf-8")


@pytest.fixture
def pasta_curta() -> Iterator[Path]:
    pasta = Path(tempfile.mkdtemp(prefix="imr-"))
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def _subir(pasta: Path, porta: PortaDeMentira, monkeypatch: pytest.MonkeyPatch,
           receita: bytes | None) -> Path:
    dados = pasta / "dados"
    dados.mkdir()
    if receita is not None:
        (dados / servidor.ARQUIVO_DA_RECEITA).write_bytes(receita)
    monkeypatch.setenv("HEFESTO_MOD_SOCKET", str(pasta / "mods.sock"))
    monkeypatch.setenv("HEFESTO_MOD_FICHA", "ficha-de-mentira")
    monkeypatch.setenv("HEFESTO_MOD_DADOS", str(dados))
    return dados


async def _rodar(pasta: Path, porta: PortaDeMentira, corpo: Any) -> int:
    socket = await asyncio.start_unix_server(porta.atender, path=str(pasta / "mods.sock"))
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


_RECEITA = {
    "formato": 1, "motor": ">=1,<2", "permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
    "sentidos": {"golpe": {"de": "jogo.vibracao", "especie": "evento", "campo": "pedido.1",
                           "escala": [0, 255], "limiar": 0.5}},
    "efeitos": {"tranco": {"canal": "motor", "forca": 1.0, "lado": "esquerdo", "dura_ms": 300}},
    "regras": [{"quando": "golpe", "entao": "tranco", "para": "quem_levou"}],
}


def test_o_processo_le_a_receita_assina_o_que_ela_usa_e_escreve_pela_porta(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, porta, monkeypatch, json.dumps(_RECEITA).encode())

    async def corpo(extensao: servidor.Extensao) -> None:
        assert not extensao.receita.universal and not extensao.receita.vazia
        await porta.publicar("jogo.vibracao", "jogo.vibracao", vibracao_do_jogo(UM, 250), UM)
        await ate(lambda: bool(porta.de("vibracao.set")))
        await ate(lambda: len(porta.de("vibracao.set")) >= 2)

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert porta.metodos[:3] == ["mod.ola", "eventos.assinar", "controles.lista"]
    assert porta.de("mod.ola") == [{"ficha": "ficha-de-mentira"}]
    assert porta.de("eventos.assinar") == [{"topicos": ["conexao", "jogo.vibracao"]}]  # (noqa-acento)
    assert porta.de("vibracao.set")[:2] == [{"uniq": UM, "fraco": 0, "forte": 255},
                                            {"uniq": UM, "fraco": 0, "forte": 0}]


@pytest.mark.parametrize("arquivo", ["campo-a-mais.json", None])
def test_sem_receita_ou_com_a_receita_recusada_vale_o_universal(
        arquivo: str | None, pasta_curta: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaDeMentira()
    bruto = (RECEITAS / arquivo).read_bytes() if arquivo else None
    _subir(pasta_curta, porta, monkeypatch, bruto)

    async def corpo(extensao: servidor.Extensao) -> None:
        assert extensao.receita.universal and not extensao.receita.vazia

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert porta.de("eventos.assinar") == [{"topicos": [  # (noqa-acento)
        "conexao", "jogo.vibracao", "jogo.haptica", "entradas", "botoes", "movimento"]}]  # (noqa-acento)
    diario = capsys.readouterr().err
    if arquivo:
        assert "foi recusada; vale o universal" in diario
        assert "linha 7: sentidos.rumble.taxa_hz: campo desconhecido" in diario
    else:
        assert "foi recusada" not in diario
    assert "a porta não entrega jogo.som, jogo.tela, microfone.nivel" in diario


def test_o_topico_que_a_porta_nao_entrega_fica_fora_da_assinatura_e_vai_ao_diario(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaDeMentira()
    receita = {"formato": 1, "motor": ">=1,<2", "permissoes": ["ler:bateria", "ler:botoes"],  # (noqa-acento)
               "sentidos": {"carga": {"de": "bateria", "especie": "nivel", "campo": "nivel"},
                            "cruz": {"de": "botoes", "especie": "evento"}}}
    _subir(pasta_curta, porta, monkeypatch, json.dumps(receita).encode())

    async def corpo(extensao: servidor.Extensao) -> None:
        assert not extensao.receita.universal and not extensao.receita.vazia

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert porta.de("eventos.assinar") == [{"topicos": ["conexao", "botoes"]}]  # (noqa-acento)
    assert "a porta não entrega bateria" in capsys.readouterr().err


def test_sem_a_porta_no_ambiente_o_processo_recusa(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in ("HEFESTO_MOD_SOCKET", "HEFESTO_MOD_FICHA"):
        monkeypatch.delenv(nome, raising=False)
    assert asyncio.run(servidor.rodar()) == 2
    assert os.environ.get("HEFESTO_MOD_SOCKET") is None
