"""O processo que o Hefesto abre para o Modo imersão: a receita, o motor e a porta.

Fala com o Hefesto pela porta das modificações (``mod.ola``, ``controles.lista``,
``eventos.assinar`` e as escritas da :class:`~motor.saida.Saida`). A receita de quem joga mora em
``$HEFESTO_MOD_DADOS/receita.json``; sem ela, ou com ela recusada, vale o universal
(``receitas/universal.json``), e a recusa vai ao diário com a linha de cada erro. Nada aqui fala
com a rede.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import sentidos as universais  # noqa: E402
from motor.laco import Motor  # noqa: E402
from motor.laco import rodar as rodar_o_laco  # noqa: E402
from motor.saida import Saida  # noqa: E402
from receita.formato import Receita, ReceitaRecusada, ler_receita, receita_vazia  # noqa: E402

ARQUIVO_DA_RECEITA = "receita.json"
ARQUIVO_DO_UNIVERSAL = AQUI / "receitas" / "universal.json"
TOPICOS_DA_PORTA = (
    "conexao", "perfil.jogo", "jogo.vibracao", "jogo.gatilho", "jogo.haptica", "entradas",  # (noqa-acento)
    "botoes", "movimento",
)


def diario(frase: str) -> None:
    """Uma linha no diário da extensão (o Hefesto guarda a saída de erro)."""
    print(frase, file=sys.stderr, flush=True)


class RecusaDaPorta(RuntimeError):
    """O ``error`` que a porta devolveu: a mensagem e o ``code`` dele."""

    def __init__(self, mensagem: str, codigo: int | None = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


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
                                codigo if isinstance(codigo, int) else None)
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


def carregar_a_receita(dados: Path | None) -> Receita:
    """A receita de quem joga, ou o universal quando ela falta ou é recusada."""
    if dados is None:
        return carregar_o_universal()
    arquivo = dados / ARQUIVO_DA_RECEITA
    try:
        bruto = arquivo.read_bytes()
    except OSError:
        return carregar_o_universal()
    try:
        return ler_receita(bruto)
    except ReceitaRecusada as exc:
        diario(f"a receita {arquivo} foi recusada; vale o universal:\n{exc}")
        return carregar_o_universal()


def _lidos(receita: Receita) -> set[str]:
    return universais.origens(s["de"] for s in receita.secao("sentidos").values())


def topicos_da_receita(receita: Receita) -> list[str]:
    """Os tópicos da porta que a receita lê (o sentido universal pelas origens dele) e que a
    porta de hoje entrega, e sempre a ``conexao``."""  # (noqa-acento)
    pedidos = _lidos(receita) | {"conexao"}  # (noqa-acento)
    return [t for t in TOPICOS_DA_PORTA if t in pedidos]


def topicos_fora_da_porta(receita: Receita) -> list[str]:
    """Os tópicos que a receita lê e que a porta de hoje não entrega: esses sentidos ficam parados."""  # (noqa-acento)
    return sorted(_lidos(receita) - set(TOPICOS_DA_PORTA))


class Extensao:
    """A porta, o motor da receita e a saída, juntos."""

    def __init__(self, porta: Porta, receita: Receita) -> None:
        self.porta = porta
        self.receita = receita
        self.motor = Motor(receita)
        self.saida = Saida(porta.pedir, diario)

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
        if topico == "conexao":  # (noqa-acento)
            with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
                await self.atualizar_os_controles()
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
    extensao = Extensao(porta, carregar_a_receita(dados))
    if fora := topicos_fora_da_porta(extensao.receita):
        diario(f"a porta não entrega {', '.join(fora)}: os sentidos desses tópicos ficam parados")
    await porta.pedir("eventos.assinar", {"topicos": topicos_da_receita(extensao.receita)})
    with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
        await extensao.atualizar_os_controles()
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

    ouvir = asyncio.create_task(ouvir_a_porta())
    motor = asyncio.create_task(rodar_o_laco(extensao.motor, extensao.saida, fim))
    try:
        await fim.wait()
        with contextlib.suppress(ConnectionError, asyncio.TimeoutError, RuntimeError):
            await asyncio.wait_for(motor, 2.0)
    finally:
        for tarefa in (ouvir, motor):
            tarefa.cancel()
        await asyncio.gather(ouvir, motor, return_exceptions=True)
        for sinal in (signal.SIGTERM, signal.SIGINT):
            with contextlib.suppress(NotImplementedError, RuntimeError):
                laco.remove_signal_handler(sinal)
        porta.fechar()
    return 0


def main() -> int:
    return asyncio.run(rodar())


if __name__ == "__main__":
    raise SystemExit(main())
