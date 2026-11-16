"""O Testar responde com o veredito de cada controle (16/11/2026).

O clique num botão de testar chega com o ``id`` da vez (a ação declara ``responde``), e a extensão
devolve pela ``extensao.resposta`` uma linha por controle conectado: ``tocou`` quando a porta
aceitou a escrita do efeito testado, e, quando não, o ``motivo`` em palavras, a frase da recusa
da porta ou o da extensão. Vale de um a quatro controles, na mesa misturada, em qualquer ordem.
"""
from __future__ import annotations

import asyncio
import json
import random
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, RAIZ, TRES, UM, EscritasDeMentira, PortaDeMentira, Recusa, ate
from test_o_universal import TIQUE, haptica_do_jogo, rumble

import opcoes as ajustes
import servidor
from receita.formato import receita_vazia

UNIQS = (UM, DOIS, TRES, QUATRO)
NATIVO = "no Modo Nativo o jogo fala direto com o controle"
TETO = "o teto de efeitos deste controle está cheio"


class PortaQueRecusa(EscritasDeMentira):
    """A porta de mentira com os controles e as recusas da porta de verdade: o ``-32011`` do Modo
    Nativo nos controles de ``nativos`` e o ``-32014`` do teto nos de ``cheios``, com a frase
    dela; guarda a ``extensao.resposta``."""

    def __init__(self, controles: list[dict[str, Any]], nativos: frozenset[str] = frozenset(),
                 cheios: frozenset[str] = frozenset()) -> None:
        super().__init__(com_haptica=True, com_som=True)
        self.controles = controles
        self.nativos = nativos
        self.cheios = cheios
        self.respostas: list[dict[str, Any]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "controles.lista":
            return {"controles": self.controles}
        if metodo in ("acessorios.estado", "eventos.assinar", "eventos.desassinar",
                      "corpo.ligar"):
            return {"status": "ok"}
        if metodo == "extensao.resposta":
            self.respostas.append(params)
            return {"entregue": True}
        uniq = params.get("uniq")
        if metodo in ("vibracao.set", "haptica.tocar", "gatilho.set"):
            if uniq in self.nativos:
                erro = Recusa(NATIVO, -32011)
                erro.dados = {"canal": metodo.split(".")[0], "modo": "nativo"}  # type: ignore[attr-defined]
                raise erro
            if uniq in self.cheios:
                erro = Recusa(TETO, -32014)
                erro.dados = {"canal": metodo.split(".")[0]}  # type: ignore[attr-defined]
                raise erro
        return await super().pedir(metodo, params)


def _mesa(n: int, ordem: int = 0) -> list[dict[str, Any]]:
    controles = [{"uniq": u, "jogador": j, "transporte": "usb" if j % 2 else "bt"}
                 for j, u in enumerate(UNIQS[:n], 1)]
    random.Random(ordem).shuffle(controles)
    return controles


def _acao(acao: str, ident: str | None = "a1") -> dict[str, Any]:
    dados: dict[str, Any] = {"mod": "imersao", "acao": acao, "alvo": None}  # (noqa-acento)
    if ident is not None:
        dados["id"] = ident
    return {"method": "evento", "params": {"topico": "extensao.acao", "nome": "extensao.acao",
                                           "uniq": None, "dados": dados}}


def _testar(porta: PortaQueRecusa, acao: str, antes: Any = None, receita: Any = None,
            ticks: int = 30, ident: str | None = "a1") -> list[dict[str, Any]]:
    async def corpo() -> None:
        extensao = servidor.Extensao(porta, receita or servidor.carregar_o_universal())  # type: ignore[arg-type]
        await extensao.atualizar_os_controles()
        if antes is not None:
            await antes(extensao)
        t = 0.0
        for _ in range(3):
            porta.agora = t
            await extensao.saida.aplicar(t, extensao.motor.passo(t))
            t += TIQUE
        await extensao.ao_evento(_acao(acao, ident))
        for _ in range(ticks):
            porta.agora = t
            await extensao.saida.aplicar(t, extensao.motor.passo(t))
            t += TIQUE
            await asyncio.sleep(0)
        if extensao.respondendo:
            await asyncio.gather(*extensao.respondendo)

    asyncio.run(corpo())
    return porta.respostas


def _por_uniq(respostas: list[dict[str, Any]]) -> dict[str, tuple[bool, str | None]]:
    [resposta] = respostas
    assert resposta["para"] == "a1"
    linhas = resposta["dados"]["controles"]
    assert all(set(linha) == {"uniq", "nome", "tocou", "motivo"} for linha in linhas)
    assert all(linha["nome"] and ":" not in linha["nome"] for linha in linhas)
    assert all(linha["motivo"] is None or 0 < len(linha["motivo"]) <= 120 for linha in linhas)
    return {linha["uniq"]: (linha["tocou"], linha["motivo"]) for linha in linhas}


@pytest.mark.parametrize("acao", sorted(ajustes.TESTES))  # (noqa-acento)
def test_a_porta_que_aceita_um_e_recusa_outro_da_os_dois_com_o_motivo(acao: str) -> None:
    porta = PortaQueRecusa(_mesa(2), nativos=frozenset({DOIS}))
    assert _por_uniq(_testar(porta, acao)) == {UM: (True, None), DOIS: (False, NATIVO)}


@pytest.mark.parametrize("n", [1, 2, 3, 4])
@pytest.mark.parametrize("ordem", [0, 1, 2])
def test_a_mesa_misturada_em_qualquer_ordem_responde_cada_controle(n: int, ordem: int) -> None:
    mesa = _mesa(n, ordem)
    nativos = frozenset(UNIQS[1:n:2])
    cheios = frozenset(UNIQS[2:n:2])
    porta = PortaQueRecusa(mesa, nativos=nativos, cheios=cheios)
    vereditos = _por_uniq(_testar(porta, "testar_golpe"))
    assert list(vereditos) == [c["uniq"] for c in mesa]
    for uniq in UNIQS[:n]:
        esperado = ((False, NATIVO) if uniq in nativos else (False, TETO) if uniq in cheios
                    else (True, None))
        assert vereditos[uniq] == esperado


def test_o_controle_desligado_na_extensao_diz_por_que_e_o_outro_toca() -> None:
    async def calar(extensao: servidor.Extensao) -> None:
        await extensao.sentir("jogador-2", False)

    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(2)), "testar_coracao", calar))
    assert vereditos == {UM: (True, None), DOIS: (False, servidor.MOTIVO_CALADO)}


@pytest.mark.parametrize("opcoes", [{"canal_haptica": False}, {ajustes.FORCA: 0}])  # (noqa-acento)
def test_o_efeito_desligado_na_janela_diz_por_que(opcoes: dict[str, Any]) -> None:
    async def desligar(extensao: servidor.Extensao) -> None:
        extensao.motor.opcoes.update(opcoes)

    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(2)), "testar_susto", desligar))
    assert vereditos == {UM: (False, servidor.MOTIVO_DESLIGADO),
                         DOIS: (False, servidor.MOTIVO_DESLIGADO)}


@pytest.mark.parametrize(("acao", "opcoes"), [("testar_coracao", {"coracao": 0}),  # (noqa-acento)
                                             ("testar_alivio", {"alivio": 0}),
                                             ("testar_golpe", {"golpe_com_lado": 0}),
                                             ("testar_susto", {"forca_do_susto": 0})])
def test_o_efeito_em_zero_na_janela_diz_que_esta_desligado(acao: str,
                                                          opcoes: dict[str, Any]) -> None:
    async def zerar(extensao: servidor.Extensao) -> None:
        extensao.motor.opcoes.update(opcoes)

    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(3)), acao, zerar))
    assert vereditos == dict.fromkeys(UNIQS[:3], (False, servidor.MOTIVO_DESLIGADO))


def test_a_forca_do_controle_em_zero_diz_por_que() -> None:
    async def zerar(extensao: servidor.Extensao) -> None:
        await extensao.nivelar(ajustes.CONTROLE_DA_FORCA, "jogador-1", "0")

    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(2)), "testar_golpe", zerar))
    assert vereditos == {UM: (False, servidor.MOTIVO_SEM_FORCA), DOIS: (True, None)}


@pytest.mark.parametrize("acao", ["testar_golpe", "testar_coracao"])  # (noqa-acento)
def test_o_jogo_que_vibra_mais_forte_ganha_e_o_teste_diz(acao: str) -> None:
    async def forte(extensao: servidor.Extensao) -> None:
        extensao.motor.evento(*rumble(UM, 255, 255))
        extensao.motor.evento(*haptica_do_jogo(UM, 1.0, 1.0))

    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(2)), acao, forte))
    assert vereditos == {UM: (False, servidor.MOTIVO_CEDEU), DOIS: (True, None)}


def test_a_receita_sem_o_efeito_diz_por_que() -> None:
    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(2)), "testar_coracao",
                                  receita=receita_vazia()))
    assert vereditos == {UM: (False, servidor.MOTIVO_SEM_O_EFEITO),
                         DOIS: (False, servidor.MOTIVO_SEM_O_EFEITO)}


def test_sem_o_laco_a_resposta_sai_no_prazo_dizendo_que_nao_chegou() -> None:
    vereditos = _por_uniq(_testar(PortaQueRecusa(_mesa(1)), "testar_golpe", ticks=0))
    assert vereditos == {UM: (False, servidor.MOTIVO_NAO_CHEGOU)}


@pytest.mark.parametrize("acao", ["testar_golpe", "testar_coracao", "testar_gatilhos"])  # (noqa-acento)
def test_o_teto_da_extensao_cheio_nao_responde_que_tocou(acao: str) -> None:
    async def encher(extensao: servidor.Extensao) -> None:
        extensao.saida.janela.extend((3 * TIQUE, UM) for _ in range(12))

    porta = PortaQueRecusa(_mesa(2))
    vereditos = _por_uniq(_testar(porta, acao, encher, ticks=1))
    assert vereditos == {UM: (False, servidor.MOTIVO_TETO), DOIS: (True, None)}
    assert not [p for _, m, p in porta.escritas if p.get("uniq") == UM
                and m in ("vibracao.set", "haptica.tocar", "gatilho.set")]


def test_o_hefesto_que_nao_manda_o_id_so_toca_e_nada_responde() -> None:
    porta = PortaQueRecusa(_mesa(2))
    assert _testar(porta, "testar_golpe", ident=None) == []
    assert porta.de("vibracao.set")


def test_o_manifesto_declara_o_responde_nos_botoes_de_testar() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    testes = [a for a in manifesto["acoes"] if a["id"] in ajustes.TESTES]  # (noqa-acento)
    assert len(testes) == len(ajustes.TESTES) and all(a.get("responde") is True for a in testes)
    assert not [a for a in manifesto["acoes"]  # (noqa-acento)
                if a["id"] not in ajustes.TESTES and "responde" in a]
    do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto")
    lido = do_hefesto.ler_manifesto(RAIZ)
    assert {a.id for a in lido.acoes if getattr(a, "responde", False)} == set(ajustes.TESTES)


class _PortaQueResponde(PortaDeMentira):
    def __init__(self) -> None:
        super().__init__()
        self.chegou = asyncio.Event()

    async def atender(self, leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        self.escritores.append(escritor)
        while linha := await leitor.readline():
            pedido = json.loads(linha)
            metodo, params = pedido["method"], pedido.get("params") or {}
            self.pedidos.append((metodo, params))
            erro = None
            resultado: Any = {"status": "ok"}
            if metodo == "controles.lista":
                resultado = {"controles": self.controles}
            elif metodo == "eventos.assinar":
                self.assinados |= set(params.get("topicos", []))
            elif metodo in ("haptica.tocar", "haptica.registrar", "som.tocar"):
                erro = {"code": -32601, "message": f"método desconhecido: {metodo}"}
            elif metodo == "vibracao.set" and params["uniq"] == DOIS:
                erro = {"code": -32011, "message": NATIVO,
                        "data": {"canal": "vibracao", "modo": "nativo"}}
            elif metodo == "extensao.resposta":
                resultado = {"entregue": True}
            resposta: dict[str, Any] = {"jsonrpc": "2.0", "id": pedido["id"]}
            resposta.update({"error": erro} if erro else {"result": resultado})
            escritor.write(json.dumps(resposta).encode() + b"\n")
            await escritor.drain()

    async def acionar(self, acao: str, ident: str) -> None:
        for escritor in self.escritores:
            escritor.write(json.dumps({"jsonrpc": "2.0", "method": "evento", "params": {
                "topico": "extensao.acao", "nome": "extensao.acao", "uniq": None,
                "dados": {"mod": "imersao", "acao": acao, "alvo": None,  # (noqa-acento)
                          "id": ident}}}).encode() + b"\n")
            await escritor.drain()


@pytest.fixture
def pasta_curta() -> Iterator[Path]:
    pasta = Path(tempfile.mkdtemp(prefix="imv-"))
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def test_pela_porta_de_verdade_a_resposta_chega_antes_de_um_segundo(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    porta = _PortaQueResponde()
    dados = pasta_curta / "dados"
    dados.mkdir()
    monkeypatch.setenv("HEFESTO_MOD_SOCKET", str(pasta_curta / "mods.sock"))
    monkeypatch.setenv("HEFESTO_MOD_FICHA", "ficha-de-mentira")
    monkeypatch.setenv("HEFESTO_MOD_DADOS", str(dados))

    async def rodar() -> tuple[float, list[dict[str, Any]]]:
        socket = await asyncio.start_unix_server(porta.atender, path=str(pasta_curta / "mods.sock"))
        extensoes: list[servidor.Extensao] = []
        processo = asyncio.create_task(servidor.rodar(extensoes.append))
        try:
            await ate(lambda: bool(extensoes))
            laco = asyncio.get_running_loop()
            inicio = laco.time()
            await porta.acionar("testar_golpe", "a7")
            await ate(lambda: bool(porta.de("extensao.resposta")), 2.0)
            return laco.time() - inicio, porta.de("extensao.resposta")
        finally:
            for escritor in porta.escritores:
                escritor.close()
            await asyncio.wait_for(processo, 5)
            socket.close()

    demora, respostas = asyncio.run(rodar())
    assert demora < 1.0
    [resposta] = respostas
    assert resposta == {"para": "a7", "dados": {"controles": [
        {"uniq": UM, "nome": "Jogador 1", "tocou": True, "motivo": None},
        {"uniq": DOIS, "nome": "Jogador 2", "tocou": False, "motivo": NATIVO}]}}
