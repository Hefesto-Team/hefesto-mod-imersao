"""A receita do jogo entra quando o jogo abre: o ``perfil.jogo`` escolhe a receita, a de quem joga
vence a estudada, o jogo sem receita e o jogo fechado ficam no universal, a troca devolve ao jogo o
que a receita velha escrevia, e as entradas da receita são opções da janela."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import threading
import time
from collections.abc import Iterator
from itertools import groupby
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ, UM, PortaDeMentira, ate

import comunidade
import servidor
from receita.biblioteca import Biblioteca
from receita.formato import ler_receita

JOGO = "steam_app_900000001"
OUTRO = "steam_app_900000002"


def _forte(chave: str | None, forca: float = 0.5) -> dict[str, Any]:
    receita: dict[str, Any] = {
        "formato": 1, "motor": ">=1,<2",
        "entradas": {"forca": {"rotulo": "Força", "tipo": "deslizante", "minimo": 0, "maximo": 1,  # (noqa-acento)
                               "padrao": forca}},  # (noqa-acento)
        "efeitos": {"tranco": {"canal": "motor", "forca": "$forca", "lado": "esquerdo"}},
        "regras": [{"quando": "$forca > 0", "entao": "tranco"}],
    }
    if chave is not None:
        receita["jogo"] = {"chave": chave}
    return receita


@pytest.fixture
def pasta_curta() -> Iterator[Path]:
    pasta = Path(tempfile.mkdtemp(prefix="imj-"))
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def _subir(pasta: Path, monkeypatch: pytest.MonkeyPatch,
           estudadas: dict[str, dict[str, Any]] | None = None,
           suas: dict[str, dict[str, Any]] | None = None,
           opcoes: dict[str, Any] | None = None) -> Path:
    dados, estudadas_dir = pasta / "dados", pasta / "estudadas"
    (dados / "receitas").mkdir(parents=True)
    estudadas_dir.mkdir()
    for nome, receita in (estudadas or {}).items():
        (estudadas_dir / nome).write_text(json.dumps(receita), encoding="utf-8")
    for nome, receita in (suas or {}).items():
        (dados / "receitas" / nome).write_text(json.dumps(receita), encoding="utf-8")
    if opcoes is not None:
        (dados / servidor.ARQUIVO_DAS_OPCOES).write_text(json.dumps(opcoes), encoding="utf-8")
    monkeypatch.setattr(servidor, "PASTA_DAS_ESTUDADAS", estudadas_dir)
    monkeypatch.setattr(servidor, "RELE_AS_OPCOES_S", 0.05)
    monkeypatch.setenv("HEFESTO_MOD_SOCKET", str(pasta / "mods.sock"))
    monkeypatch.setenv("HEFESTO_MOD_FICHA", "ficha-de-mentira")
    monkeypatch.setenv("HEFESTO_MOD_DADOS", str(dados))
    monkeypatch.setattr(comunidade, "baixar_da_internet", _sem_internet)
    return dados


def _sem_internet(endereco: str, teto: int) -> bytes:
    raise OSError(f"as provas não saem para a internet: {endereco}")


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


async def _abrir(porta: PortaDeMentira, jogo: str | None) -> None:
    await porta.publicar("perfil.jogo", "perfil.trocou", {
        "perfil": "Padrão", "jogo": jogo, "estilo": None, "controles": [], "t": 1.0})


def _fortes(porta: PortaDeMentira) -> list[int]:
    return [p["forte"] for p in porta.de("vibracao.set") if p["uniq"] == UM]


def test_o_jogo_com_receita_estudada_troca_para_ela_e_o_fechado_volta_ao_universal(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, monkeypatch, estudadas={"o-jogo.json": _forte(JOGO)})

    async def corpo(extensao: servidor.Extensao) -> None:
        assert extensao.escolhida.origem == "universal"
        assert "perfil.jogo" in porta.assinados
        await _abrir(porta, JOGO)
        await ate(lambda: extensao.escolhida.origem == "estudada")
        await ate(lambda: 128 in _fortes(porta))
        await _abrir(porta, None)
        await ate(lambda: extensao.escolhida.origem == "universal")
        await ate(lambda: _fortes(porta)[-1:] == [0])

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert porta.de("acessorios.estado")[0]["perfil"] == "Universal"
    assert [k for k, _ in groupby(e["perfil"] for e in porta.de("acessorios.estado"))] == [
        "Universal", "Receita estudada", "Universal"]


def test_o_jogo_sem_receita_fica_no_universal(pasta_curta: Path,
                                              monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, monkeypatch, estudadas={"o-jogo.json": _forte(JOGO)})

    async def corpo(extensao: servidor.Extensao) -> None:
        await _abrir(porta, OUTRO)
        await ate(lambda: extensao.jogo == OUTRO)
        await asyncio.sleep(0.2)
        assert extensao.escolhida.origem == "universal"
        assert extensao.motor.receita.universal

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert not _fortes(porta)


def test_a_receita_de_quem_joga_vence_a_estudada(pasta_curta: Path,
                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, monkeypatch, estudadas={"o-jogo.json": _forte(JOGO, 0.5)},
           suas={"minha.json": _forte(JOGO, 1.0)})

    async def corpo(extensao: servidor.Extensao) -> None:
        await _abrir(porta, JOGO)
        await ate(lambda: extensao.escolhida.origem == "sua")
        await ate(lambda: 255 in _fortes(porta))

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert 128 not in _fortes(porta)
    assert porta.de("acessorios.estado")[-1]["perfil"] == "Sua receita"


def test_a_opcao_universal_sempre_ignora_a_receita_do_jogo(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, monkeypatch, estudadas={"o-jogo.json": _forte(JOGO)},
           opcoes={"receita": "Universal"})

    async def corpo(extensao: servidor.Extensao) -> None:
        await _abrir(porta, JOGO)
        await ate(lambda: extensao.jogo == JOGO)
        await asyncio.sleep(0.2)
        assert extensao.escolhida.origem == "universal"

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
    assert not _fortes(porta)


def test_a_opcao_de_uma_entrada_muda_o_que_o_motor_escreve(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    dados = _subir(pasta_curta, monkeypatch, estudadas={"o-jogo.json": _forte(JOGO)})

    async def corpo(extensao: servidor.Extensao) -> None:
        await _abrir(porta, JOGO)
        await ate(lambda: 128 in _fortes(porta))
        (dados / servidor.ARQUIVO_DAS_OPCOES).write_text(json.dumps({"forca": 0.2}),
                                                         encoding="utf-8")
        await ate(lambda: _fortes(porta)[-1:] == [51])
        await extensao.ao_evento({"method": "evento", "params": {
            "topico": "extensao.opcao", "nome": "extensao.opcao", "uniq": None,
            "dados": {"mod": "imersao", "id": "forca", "valor": 0.8}}})
        await ate(lambda: _fortes(porta)[-1:] == [204])

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0


def test_a_receita_recusada_nao_vale_e_o_diario_diz_a_linha(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    linhas: list[str] = []
    estudadas = pasta_curta / "estudadas"
    estudadas.mkdir()
    (estudadas / "torta.json").write_text(
        '{\n"formato": 1,\n"motor": ">=1,<2",\n"jogo": {"chave": "' + JOGO + '"},\n"sobra": 1\n}',
        encoding="utf-8")
    biblioteca = Biblioteca(estudadas, None, servidor.carregar_o_universal, linhas.append)
    assert biblioteca.para(JOGO).origem == "universal"
    assert "linha 5" in linhas[0] and "torta.json" in linhas[0]


def test_toda_entrada_das_receitas_da_extensao_e_uma_opcao_da_janela() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    opcoes = {o["id"]: o for o in manifesto["opcoes"]}  # (noqa-acento)
    assert opcoes["receita"]["escolhas"] == ["Pelo jogo", "Universal"]
    assert "perfil" in manifesto["agora"] and "publicar:acessorios.estado" in manifesto[
        "permissoes"]  # (noqa-acento)
    arquivos = [RAIZ / "receitas" / "universal.json",
                *sorted((RAIZ / "receitas" / "estudadas").glob("*.json"))]
    for arquivo in arquivos:
        for ident, entrada in ler_receita(arquivo.read_bytes()).secao("entradas").items():
            opcao = opcoes.get(ident)
            assert opcao is not None, f"{arquivo.name}: a entrada {ident} não é opção"
            assert opcao["tipo"] == entrada["tipo"]
            assert opcao["padrao"] == entrada["padrao"]  # (noqa-acento)
            if entrada["tipo"] == "deslizante":
                assert (opcao["minimo"], opcao["maximo"]) == (entrada["minimo"],  # (noqa-acento)
                                                              entrada["maximo"])  # (noqa-acento)


def test_a_saida_nao_espera_a_procura_da_comunidade_na_rede_lenta(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, monkeypatch)
    solta = threading.Event()

    def lenta(endereco: str, teto: int) -> bytes:
        solta.wait(10)
        raise OSError(f"a rede não respondeu: {endereco}")

    monkeypatch.setattr(comunidade, "baixar_da_internet", lenta)

    async def corpo(extensao: servidor.Extensao) -> None:
        await _abrir(porta, JOGO)
        await ate(lambda: extensao.procurando is not None)

    inicio = time.monotonic()
    try:
        assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0
        assert time.monotonic() - inicio < 3
    finally:
        solta.set()
