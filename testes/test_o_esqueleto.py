"""O esqueleto da extensão: o manifesto pelo validador do Hefesto, a licença e o processo inteiro
falando com a porta de mentira num socket."""
from __future__ import annotations

import asyncio
import contextlib
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
    assert [p for p in manifesto.permissoes if p.startswith("rede:")] == ["rede:internet"]
    assert [p for p in manifesto.permissoes if p.startswith("publicar:")] == [
        "publicar:acessorios.estado"]


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
    assert porta.de("eventos.assinar") == [{"topicos": [  # (noqa-acento)
        "conexao", "perfil.jogo", "jogo.vibracao", "jogo.identidade", "jogo.estilo"]}]  # (noqa-acento)
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
        "conexao", "perfil.jogo", "jogo.vibracao", "jogo.gatilho", "jogo.haptica", "entradas", "botoes",  # (noqa-acento)
        "movimento", "jogo.som", "microfone.nivel", "jogo.identidade", "jogo.estilo"]}]  # (noqa-acento)
    diario = capsys.readouterr().err
    if arquivo:
        assert "foi recusada e não vale" in diario
        assert "linha 7: sentidos.rumble.taxa_hz: campo desconhecido" in diario
    else:
        assert "foi recusada" not in diario
    assert "a porta não entrega" not in diario


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
    assert porta.de("eventos.assinar") == [{"topicos": ["conexao", "perfil.jogo", "botoes",  # (noqa-acento)
                                                       "jogo.estilo"]}]
    assert "a porta não entrega bateria" in capsys.readouterr().err


def test_sem_a_porta_no_ambiente_o_processo_recusa(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in ("HEFESTO_MOD_SOCKET", "HEFESTO_MOD_FICHA"):
        monkeypatch.delenv(nome, raising=False)
    assert asyncio.run(servidor.rodar()) == 2
    assert os.environ.get("HEFESTO_MOD_SOCKET") is None


TAREFAS_DE_FUNDO = ("ouvir", "vigiar", "clima", "resumo", "cor", "motor")


def _falhar_na_tarefa(nome: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Faz a tarefa ``nome`` de ``servidor.rodar`` levantar na primeira vez que chega a ela."""
    def a_tarefa() -> str:
        atual = asyncio.current_task()
        return atual.get_name() if atual is not None else ""

    def cair(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError(f"queda forçada em {nome}")

    monkeypatch.setattr(servidor, "PUBLICA_O_CLIMA_S", 0.01)
    monkeypatch.setattr(servidor, "RESUMO_A_CADA_S", 0.01)
    monkeypatch.setattr(servidor, "RELE_OS_CONTROLES_S", 0.01)
    if nome == "vigiar":
        monkeypatch.setattr(servidor, "_marca_das_opcoes", cair)
    elif nome == "motor":
        async def laco(*_args: Any, **_kwargs: Any) -> None:
            cair()

        monkeypatch.setattr(servidor, "rodar_o_laco", laco)
    elif nome == "ouvir":
        monkeypatch.setattr(servidor.Extensao, "ao_evento", cair)
    else:
        for metodo in ("publicar_se_mudou", "rever_os_controles"):
            original = getattr(servidor.Extensao, metodo)

            async def depende(eu: Any, *args: Any, _o: Any = original, _m: str = metodo,
                              **kwargs: Any) -> Any:
                if a_tarefa() == nome:
                    cair()
                return await _o(eu, *args, **kwargs)

            monkeypatch.setattr(servidor.Extensao, metodo, depende)


@pytest.mark.parametrize("nome", TAREFAS_DE_FUNDO)
def test_a_tarefa_de_fundo_que_cai_encerra_a_extensao_com_o_traceback_no_diario(
        nome: str, pasta_curta: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, porta, monkeypatch, None)
    _falhar_na_tarefa(nome, monkeypatch)

    async def correr() -> int:
        socket = await asyncio.start_unix_server(porta.atender, path=str(pasta_curta / "mods.sock"))
        extensoes: list[servidor.Extensao] = []
        processo = asyncio.create_task(servidor.rodar(extensoes.append))
        try:
            await ate(lambda: bool(extensoes))
            if nome == "ouvir":
                extensoes[0].porta.eventos.put_nowait({"method": "evento", "params": {
                    "topico": "botoes", "nome": "button.down", "uniq": UM, "dados": {}}})
            try:
                return await asyncio.wait_for(asyncio.shield(processo), 2)
            except asyncio.TimeoutError:
                pytest.fail(f"a extensão seguiu viva com a tarefa {nome} caída")
        finally:
            for escritor in porta.escritores:
                escritor.close()
            socket.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(processo, 5)

    assert asyncio.run(correr()) == 1
    diario = capsys.readouterr().err
    assert f"a tarefa {nome} caiu" in diario and f"queda forçada em {nome}" in diario
    assert "Traceback" in diario


def test_a_porta_fechada_com_a_tarefa_ouvir_morta_encerra_o_processo_e_nao_deixa_pedido_preso(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = PortaDeMentira()
    _subir(pasta_curta, porta, monkeypatch, None)
    monkeypatch.setattr(servidor, "PRAZO_DO_PEDIDO_S", 0.05)

    async def corpo(extensao: servidor.Extensao) -> None:
        for escritor in porta.escritores:
            escritor.close()
        await ate(lambda: extensao.porta.fechada)
        assert extensao.porta._esperando == {}

    assert asyncio.run(_rodar(pasta_curta, porta, corpo)) == 0


async def _servir(pasta: Path, resposta: Any) -> Any:
    return await asyncio.start_unix_server(resposta, path=str(pasta / "linha.sock"))


def test_o_leitor_que_morre_por_qualquer_causa_marca_a_porta_como_fechada() -> None:
    class Leitor:
        async def readline(self) -> bytes:
            raise RuntimeError("leitor quebrado")

    class Escritor:
        def close(self) -> None:
            pass

    async def correr() -> tuple[bool, list[dict[str, Any]]]:
        porta = servidor.Porta(Leitor(), Escritor())  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="leitor quebrado"):
            await porta._lendo
        avisos = [porta.eventos.get_nowait() for _ in range(porta.eventos.qsize())]
        return porta.fechada, avisos

    fechada, avisos = asyncio.run(correr())
    assert fechada and avisos == [{"method": "porta.fechou"}]


def test_a_linha_de_mais_de_1_mib_nao_derruba_o_leitor_da_porta(pasta_curta: Path) -> None:
    async def correr() -> tuple[bool, list[Any]]:
        async def atender(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
            escritor.write(b"x" * (3 << 20) + b"\n")
            escritor.write(json.dumps({"method": "evento", "params": {"topico": "conexao"}}
                                      ).encode() + b"\n")
            await escritor.drain()
            await leitor.read()

        socket = await _servir(pasta_curta, atender)
        porta = await servidor.Porta.abrir(str(pasta_curta / "linha.sock"))
        try:
            mensagem = await asyncio.wait_for(porta.eventos.get(), 3)
            return porta.fechada, [mensagem]
        finally:
            porta.fechar()
            socket.close()

    fechada, mensagens = asyncio.run(correr())
    assert not fechada
    assert mensagens[0]["params"]["topico"] == "conexao"


def test_o_pedido_que_estoura_o_prazo_sai_da_fila_de_espera(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(servidor, "PRAZO_DO_PEDIDO_S", 0.05)

    async def correr() -> dict[int, Any]:
        async def calado(leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
            await leitor.read()

        socket = await _servir(pasta_curta, calado)
        porta = await servidor.Porta.abrir(str(pasta_curta / "linha.sock"))
        try:
            with pytest.raises(asyncio.TimeoutError):
                await porta.pedir("mod.ola", {})
            return dict(porta._esperando)
        finally:
            porta.fechar()
            socket.close()

    assert asyncio.run(correr()) == {}


@pytest.mark.parametrize("valor", [[], {}, 3, None, ["terror"]])
def test_o_estilo_que_nao_e_texto_no_opcoes_nao_derruba_a_extensao(
        valor: Any, pasta_curta: Path) -> None:
    from receita import estilos

    dados = pasta_curta / "dados"
    dados.mkdir()
    (dados / servidor.ARQUIVO_DAS_OPCOES).write_text(json.dumps({estilos.OPCAO: valor}),
                                                      encoding="utf-8")
    extensao = servidor.Extensao(PortaMuda(), servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                 None, dados)
    assert extensao.preset is None
    extensao.estilo_dito = True
    extensao.aplicar_o_estilo()
    assert extensao.preset == estilos.GERAL


class PortaMuda:
    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}
