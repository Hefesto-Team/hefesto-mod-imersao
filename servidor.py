"""O processo que o Hefesto abre para o Modo imersão: a receita, o motor e a porta.

Fala com o Hefesto pela porta das modificações (``mod.ola``, ``controles.lista``,
``eventos.assinar``, ``acessorios.estado`` e as escritas da :class:`~motor.saida.Saida`). A
receita se escolhe pelo jogo aberto (``perfil.jogo``), na
:class:`~receita.biblioteca.Biblioteca`: a de quem joga, a estudada, a da comunidade e, sem
nenhuma, o universal (``receitas/universal.json``); a recusa vai ao diário com a linha de cada erro.
A troca vale no tique seguinte, e o que a receita velha escrevia volta ao jogo. As opções da janela
moram em ``$HEFESTO_MOD_DADOS/opcoes.json``: a opção ``receita`` (pelo jogo, ou o universal
sempre) e as entradas das receitas, relidas a cada mudança do arquivo e, no arrastar, pelo
``extensao.opcao``. A coluna «Agora» da janela diz de onde veio a receita que vale. Além do que a
receita lê, assina o que o jogo escreve nos canais em que ela escreve, para o motor medir o caminho
do controle (``jogo.identidade`` entra quando a porta o entregar). O
:class:`~estudio.cacador.Estudio` fala com a página pelo ``extensao.mensagem`` e responde pelo
``extensao.resposta``; enquanto caça, ouve o ``jogo.som`` e toma o botão do meio como marca do gesto.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import sentidos as universais  # noqa: E402
from estudio.cacador import Estudio  # noqa: E402
from motor.caminho import CANAIS as CANAIS_DO_JOGO  # noqa: E402
from motor.laco import Motor  # noqa: E402
from motor.laco import rodar as rodar_o_laco  # noqa: E402
from motor.saida import Saida  # noqa: E402
from receita.biblioteca import (  # noqa: E402
    ARQUIVO_DE_ANTES,
    PELO_JOGO,
    Biblioteca,
    Escolhida,
)
from receita.formato import Receita, ReceitaRecusada, ler_receita, receita_vazia  # noqa: E402

ARQUIVO_DA_RECEITA = ARQUIVO_DE_ANTES
ARQUIVO_DO_UNIVERSAL = AQUI / "receitas" / "universal.json"
PASTA_DAS_ESTUDADAS = AQUI / "receitas" / "estudadas"
ARQUIVO_DAS_OPCOES = "opcoes.json"
OPCAO_DA_RECEITA = "receita"
RELE_AS_OPCOES_S = 0.5
TOPICOS_DA_PORTA = (
    "conexao", "perfil.jogo", "jogo.vibracao", "jogo.gatilho", "jogo.haptica", "entradas",  # (noqa-acento)
    "botoes", "movimento",
)
TOPICOS_DO_ESTUDIO = ("botoes", "jogo.som")
BOTAO_DA_MARCA = "ps"
CAMINHO_POR_CANAL = (
    ("motor", "jogo.vibracao"), ("haptica", "jogo.vibracao"), ("haptica", "jogo.haptica"),
    ("gatilho", "jogo.gatilho"),
)


def diario(frase: str) -> None:
    """Uma linha no diário da extensão (o Hefesto guarda a saída de erro)."""
    print(frase, file=sys.stderr, flush=True)


class RecusaDaPorta(RuntimeError):
    """O ``error`` que a porta devolveu: a mensagem, o ``code`` e o ``data`` dele."""

    def __init__(self, mensagem: str, codigo: int | None = None, dados: Any = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.dados = dados


class Porta:
    """O cliente da porta das modificações: JSON-RPC 2.0, um objeto por linha."""

    def __init__(self, leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        self._leitor = leitor
        self._escritor = escritor
        self._proximo = 0
        self._esperando: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.eventos: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.fechada = False
        self._lendo = asyncio.create_task(self._ler())

    @classmethod
    async def abrir(cls, caminho: str) -> Porta:
        leitor, escritor = await asyncio.open_unix_connection(caminho, limit=1 << 20)
        return cls(leitor, escritor)

    async def _ler(self) -> None:
        with contextlib.suppress(ConnectionError):
            while linha := await self._leitor.readline():
                try:
                    mensagem = json.loads(linha)
                except ValueError:
                    continue
                if not isinstance(mensagem, dict):
                    continue
                ident = mensagem.get("id")
                espera = self._esperando.pop(ident, None) if isinstance(ident, int) else None
                if espera is not None and not espera.done():
                    espera.set_result(mensagem)
                elif "method" in mensagem:
                    await self.eventos.put(mensagem)
        self.fechada = True
        for espera in self._esperando.values():
            if not espera.done():
                espera.set_exception(ConnectionError("a porta fechou"))
        await self.eventos.put({"method": "porta.fechou"})

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        """O ``result`` do pedido; o ``error`` da porta vira :class:`RecusaDaPorta`."""
        if self.fechada:
            raise ConnectionError("a porta fechou")
        self._proximo += 1
        espera: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._esperando[self._proximo] = espera
        linha = {"jsonrpc": "2.0", "id": self._proximo, "method": metodo, "params": params}
        self._escritor.write(json.dumps(linha).encode() + b"\n")
        await self._escritor.drain()
        resposta = await asyncio.wait_for(espera, 10)
        if "error" in resposta:
            erro = resposta["error"] if isinstance(resposta["error"], dict) else {}
            codigo = erro.get("code")
            raise RecusaDaPorta(str(erro.get("message", "recusado")),
                                codigo if isinstance(codigo, int) else None, erro.get("data"))
        resultado: dict[str, Any] = resposta.get("result") or {}
        return resultado

    def fechar(self) -> None:
        self._lendo.cancel()
        self._escritor.close()


def carregar_o_universal(arquivo: Path = ARQUIVO_DO_UNIVERSAL) -> Receita:
    """A receita que vale em todo jogo; sem ela legível, a vazia, e o diário diz por quê."""
    try:
        return replace(ler_receita(arquivo.read_bytes()), universal=True)
    except (OSError, ReceitaRecusada) as exc:
        diario(f"o universal {arquivo} não se leu; nada toca:\n{exc}")
        return receita_vazia()


def _lidos(receita: Receita) -> set[str]:
    return universais.origens(s["de"] for s in receita.secao("sentidos").values())


def topicos_do_caminho(receita: Receita) -> set[str]:
    """O que o jogo escreve nos canais em que a receita escreve: o caminho medido pelo motor."""
    canais = {e["canal"] for e in receita.secao("efeitos").values()}
    topicos = {t for canal, t in CAMINHO_POR_CANAL if canal in canais}
    return topicos | ({"jogo.identidade"} if canais & set(CANAIS_DO_JOGO) else set())


def topicos_da_receita(receita: Receita) -> list[str]:
    """Os tópicos da porta que a receita lê (o sentido universal pelas origens dele), os do
    caminho dos canais em que ela escreve e sempre o das conexões, quando a porta de hoje os
    entrega."""
    pedidos = _lidos(receita) | topicos_do_caminho(receita) | {"conexao"}  # (noqa-acento)
    return [t for t in TOPICOS_DA_PORTA if t in pedidos]


def topicos_assinados(receita: Receita) -> list[str]:
    """Os tópicos da receita e sempre o ``perfil.jogo``: é ele que diz qual receita vale."""
    pedidos = set(topicos_da_receita(receita)) | {"perfil.jogo"}
    return [t for t in TOPICOS_DA_PORTA if t in pedidos]


def ler_as_opcoes(dados: Path | None) -> dict[str, Any]:
    """O ``opcoes.json`` que a janela grava, ``{id: valor}``; vazio quando falta ou não se lê."""
    if dados is None:
        return {}
    try:
        lidas = json.loads((dados / ARQUIVO_DAS_OPCOES).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return lidas if isinstance(lidas, dict) else {}


def topicos_fora_da_porta(receita: Receita) -> list[str]:
    """Os tópicos que a receita lê e que a porta de hoje não entrega: esses sentidos ficam parados."""  # (noqa-acento)
    return sorted(_lidos(receita) - set(TOPICOS_DA_PORTA))


class Extensao:
    """A porta, o motor da receita e a saída, juntos."""

    def __init__(self, porta: Porta, receita: Receita | Escolhida,
                 biblioteca: Biblioteca | None = None, dados: Path | None = None) -> None:
        self.porta = porta
        self.escolhida = receita if isinstance(receita, Escolhida) else Escolhida(
            receita, "universal" if receita.universal else "sua")
        self.receita = self.escolhida.receita
        self.biblioteca = biblioteca
        self.dados = dados
        self.jogo: str | None = None
        self.opcoes = ler_as_opcoes(dados)
        self.motor = Motor(self.receita, self.opcoes)
        self.saida = Saida(porta.pedir, diario, self.motor.recusado, self.motor.pelo_motor)
        self.assinados: set[str] = set()
        self.estados_publicados: list[str] = []
        self.estudio = Estudio(porta.pedir, dados / "receitas" if dados else None, ler_receita)

    @property
    def escolha(self) -> str:
        valor = self.opcoes.get(OPCAO_DA_RECEITA, PELO_JOGO)
        return valor if isinstance(valor, str) else PELO_JOGO

    async def assinar(self) -> None:
        """Assina o que a receita de agora lê e ainda não estava assinado."""
        faltam = [t for t in topicos_assinados(self.receita) if t not in self.assinados]
        if faltam:
            await self.porta.pedir("eventos.assinar", {"topicos": faltam})
            self.assinados |= set(faltam)

    async def assinar_o_estudio(self) -> None:
        """O Estúdio ouve o som do jogo e o botão do meio enquanto caça."""
        for topico in TOPICOS_DO_ESTUDIO:
            if topico in self.assinados:
                continue
            with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
                await self.porta.pedir("eventos.assinar", {"topicos": [topico]})
                self.assinados.add(topico)

    async def responder_ao_estudio(self, resposta: dict[str, Any] | None,
                                   pedido: Any = None) -> None:
        """A resposta do Estúdio volta à página pela porta (``extensao.resposta``)."""
        if resposta is None:
            return
        params: dict[str, Any] = {"dados": resposta}
        if pedido is not None:
            params["id"] = pedido
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.porta.pedir("extensao.resposta", params)

    async def ao_estudio(self, topico: str, nome: Any, dados: dict[str, Any]) -> None:
        """Os eventos que o Estúdio usa: a mensagem da página, o som e o botão da marca."""
        agora_ms = time.monotonic() * 1000.0
        if topico == "extensao.mensagem":
            pedido = dados.get("dados", dados)
            if isinstance(pedido, dict):
                if pedido.get("tipo") == "comecar":
                    await self.assinar_o_estudio()
                await self.responder_ao_estudio(await self.estudio.mensagem(pedido, agora_ms),
                                                dados.get("id"))
        elif topico == "jogo.som":
            self.estudio.ouvir(dados, agora_ms)
        elif (topico == "botoes" and nome == "button.down" and self.estudio.ativo
              and BOTAO_DA_MARCA in (dados.get("botao"), dados.get("button"))):
            await self.responder_ao_estudio(await self.estudio.marca(agora_ms))

    async def publicar_o_estado(self) -> None:
        """A coluna «Agora» da janela: de onde veio a receita que vale."""
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.porta.pedir("acessorios.estado", {
                "ligado": True, "nivel": 0, "perfil": self.escolhida.rotulo,
                "aparelhos": [], "conexoes": []})  # (noqa-acento)
            self.estados_publicados.append(self.escolhida.rotulo)

    async def escolher(self) -> None:
        """A receita do jogo de agora; quando muda, o motor a troca no tique seguinte."""
        if self.biblioteca is None:
            return
        nova = self.biblioteca.para(self.jogo, self.escolha)
        if nova.marca == self.escolhida.marca and nova.receita.dados == self.receita.dados:
            return
        self.escolhida, self.receita = nova, nova.receita
        self.motor.trocar(nova.receita)
        diario(f"vale a receita {nova.arquivo or 'universal'} ({nova.rotulo})")
        if fora := topicos_fora_da_porta(nova.receita):
            diario(f"a porta não entrega {', '.join(fora)}: os sentidos desses tópicos ficam parados")
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.assinar()
        await self.publicar_o_estado()

    async def reler_as_opcoes(self) -> None:
        """O ``opcoes.json`` mudou: as entradas valem já, e a opção da receita pode trocá-la."""
        self.opcoes = ler_as_opcoes(self.dados)
        self.motor.ajustar(self.opcoes)
        await self.escolher()

    async def atualizar_os_controles(self) -> None:
        resposta = await self.porta.pedir("controles.lista", {})
        lista = resposta.get("controles", [])
        self.motor.controles(lista if isinstance(lista, list) else [])

    async def ao_evento(self, mensagem: dict[str, Any]) -> bool:
        """Leva o evento ao motor; ``False`` quando a porta fechou."""
        if mensagem.get("method") == "porta.fechou":
            return False
        params = mensagem.get("params")
        if mensagem.get("method") != "evento" or not isinstance(params, dict):
            return True
        topico, nome = params.get("topico"), params.get("nome")
        dados = params.get("dados")
        if topico == "conexao":  # (noqa-acento)
            with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
                await self.atualizar_os_controles()
        elif topico == "perfil.jogo" and isinstance(dados, dict):
            jogo = dados.get("jogo")
            self.jogo = jogo if isinstance(jogo, str) and jogo else None
            self.estudio.jogo = self.jogo
            self.estudio.memoria_ligada = dados.get("memoria") is True
            await self.escolher()
        elif topico == "extensao.opcao" and isinstance(dados, dict):
            ident, valor = dados.get("id"), dados.get("valor")
            if isinstance(ident, str) and isinstance(valor, (int, float)):
                self.motor.opcoes[ident] = valor
        if isinstance(topico, str) and isinstance(dados, dict):
            await self.ao_estudio(topico, nome, dados)
        if isinstance(topico, str) and isinstance(nome, str):
            uniq = params.get("uniq")
            dados = params.get("dados")
            self.motor.evento(topico, nome, uniq if isinstance(uniq, str) else None,
                              dados if isinstance(dados, dict) else {})
        return True


async def rodar(ao_nascer: Callable[[Extensao], None] | None = None) -> int:
    """O processo inteiro; ``ao_nascer`` recebe a extensão pronta (as provas o usam)."""
    caminho, ficha = os.environ.get("HEFESTO_MOD_SOCKET"), os.environ.get("HEFESTO_MOD_FICHA")
    if not caminho or not ficha:
        diario("sem HEFESTO_MOD_SOCKET e HEFESTO_MOD_FICHA: quem abre esta extensão é o Hefesto")
        return 2
    dados = Path(os.environ["HEFESTO_MOD_DADOS"]) if os.environ.get("HEFESTO_MOD_DADOS") else None
    porta = await Porta.abrir(caminho)
    await porta.pedir("mod.ola", {"ficha": ficha})
    biblioteca = Biblioteca(PASTA_DAS_ESTUDADAS, dados, carregar_o_universal, diario)
    opcoes = ler_as_opcoes(dados)
    escolha = opcoes.get(OPCAO_DA_RECEITA, PELO_JOGO)
    extensao = Extensao(porta, biblioteca.para(None, escolha if isinstance(escolha, str) else
                                               PELO_JOGO), biblioteca, dados)
    if fora := topicos_fora_da_porta(extensao.receita):
        diario(f"a porta não entrega {', '.join(fora)}: os sentidos desses tópicos ficam parados")
    await extensao.assinar()
    with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
        await extensao.atualizar_os_controles()
    await extensao.publicar_o_estado()
    if ao_nascer is not None:
        ao_nascer(extensao)

    fim = asyncio.Event()
    laco = asyncio.get_running_loop()
    for sinal in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            laco.add_signal_handler(sinal, fim.set)

    async def ouvir_a_porta() -> None:
        while await extensao.ao_evento(await porta.eventos.get()):
            pass
        fim.set()

    async def vigiar_as_opcoes() -> None:
        marca = _marca_das_opcoes(dados)
        while True:
            await asyncio.sleep(RELE_AS_OPCOES_S)
            agora = _marca_das_opcoes(dados)
            if agora != marca:
                marca = agora
                await extensao.reler_as_opcoes()

    ouvir = asyncio.create_task(ouvir_a_porta())
    vigiar = asyncio.create_task(vigiar_as_opcoes())
    motor = asyncio.create_task(rodar_o_laco(extensao.motor, extensao.saida, fim))
    try:
        await fim.wait()
        with contextlib.suppress(ConnectionError, asyncio.TimeoutError, RuntimeError):
            await asyncio.wait_for(motor, 2.0)
    finally:
        for tarefa in (ouvir, vigiar, motor):
            tarefa.cancel()
        await asyncio.gather(ouvir, vigiar, motor, return_exceptions=True)
        for sinal in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                laco.remove_signal_handler(sinal)
        porta.fechar()
    return 0


def _marca_das_opcoes(dados: Path | None) -> tuple[int, int] | None:
    if dados is None:
        return None
    try:
        estado = (dados / ARQUIVO_DAS_OPCOES).stat()
    except OSError:
        return None
    return (estado.st_mtime_ns, estado.st_size)


def main() -> int:
    return asyncio.run(rodar())


if __name__ == "__main__":
    raise SystemExit(main())
