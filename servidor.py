"""O processo que o Hefesto abre para o Modo imersão: a receita, o motor e a porta.

Fala com o Hefesto pela porta das modificações (``mod.ola``, ``controles.lista``,
``eventos.assinar``, ``acessorios.estado`` e as escritas da :class:`~motor.saida.Saida`). A
receita se escolhe pelo jogo aberto (``perfil.jogo``), na
:class:`~receita.biblioteca.Biblioteca`: a de quem joga, a estudada, a da comunidade e, sem
nenhuma, o universal (``receitas/universal.json``); a recusa vai ao diário com a linha de cada erro.
A troca vale no tique seguinte, e o que a receita velha escrevia volta ao jogo. As opções da janela
moram em ``$HEFESTO_MOD_DADOS/opcoes.json``: a opção ``receita`` (pelo jogo, ou o universal
sempre) e as entradas das receitas, relidas a cada mudança do arquivo e, no arrastar, pelo
``extensao.opcao``. A coluna «Agora» da janela diz de onde veio a receita que vale e o clima da
cena no nível; cada controle conectado é um cartão na aba Geral, e o desligado não recebe efeito
(``controles.json``). Além do que a
receita lê, assina o que o jogo escreve nos canais em que ela escreve, para o motor medir o caminho
do controle e a máscara do lançamento (``jogo.identidade``). Os sentidos e os canais desligados na
janela (``opcoes.py``) desassinam o tópico deles e calam o que escrevem; o ``jogo.tela`` nasce
desligado, porque assiná-lo abre o portal de captura do sistema, e se liga quando a pessoa
ensina pela tela uma receita que o lê. O
:class:`~estudio.cacador.Estudio` fala com a página pelo ``extensao.mensagem`` e responde pelo
``extensao.resposta``; enquanto caça, ouve o ``jogo.som`` e toma o botão do meio como marca do gesto.
A :class:`~comunidade.Comunidade` procura a receita do jogo aberto no índice assinado a cada jogo
que abre (o índice se baixa uma vez por dia), no «Procurar receitas» da página e no botão da
aba Geral da janela (``extensao.acao``); a leitura da
memória da receita da comunidade só chega ao motor com a chave «Memória» dela ligada.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:
    sys.path.insert(0, str(AQUI))

import opcoes as ajustes  # noqa: E402
import sentidos as universais  # noqa: E402
from comunidade import TIPOS_DA_COMUNIDADE, Comunidade  # noqa: E402
from estudio import linha_do_tempo  # noqa: E402
from estudio.blocos import TIPOS_DO_MONTADOR, Montador  # noqa: E402
from estudio.cacador import Estudio  # noqa: E402
from estudio.grafo import TIPOS_DO_EDITOR, Editor  # noqa: E402
from estudio.linha_do_tempo import TIPOS_DO_GRAVADOR, Gravador  # noqa: E402
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
ARQUIVO_DAS_OPCOES = ajustes.ARQUIVO_DAS_OPCOES
OPCAO_DA_RECEITA = "receita"
ACAO_DE_PROCURAR = "procurar"
RELE_AS_OPCOES_S = 0.5
PUBLICA_O_CLIMA_S = 0.5
TOPICOS_DA_PORTA = (
    "conexao", "perfil.jogo", "jogo.vibracao", "jogo.gatilho", "jogo.haptica", "entradas",  # (noqa-acento)
    "botoes", "movimento", "jogo.som", "microfone.nivel", "jogo.tela", "jogo.identidade",
    "jogo.memoria",
)
TOPICOS_DO_ESTUDIO = ("botoes", "jogo.som")
BOTAO_DA_MARCA = "ps"
RESPOSTAS_QUE_GRAVAM = ("guardado", "montado", "importado")
FALHAS_DO_ESTUDIO = (RuntimeError, OSError, ValueError, asyncio.TimeoutError)
FRASE_DA_FALHA = "não deu agora"
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


def topicos_assinados(receita: Receita, opcoes: dict[str, Any] | None = None) -> list[str]:
    """Os tópicos da receita e sempre o ``perfil.jogo``: é ele que diz qual receita vale."""
    pedidos = set(topicos_da_receita(receita)) | {"perfil.jogo"}
    return [t for t in TOPICOS_DA_PORTA if t in pedidos and ajustes.topico_ligado(t, opcoes)]


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


async def em_fio_solto(trabalho: Callable[..., Any], *args: Any) -> Any:
    """``trabalho`` num fio daemon: a rede lenta não segura a saída do processo."""
    laco = asyncio.get_running_loop()
    feito: asyncio.Future[Any] = laco.create_future()

    def entregar(resultado: Any, erro: BaseException | None) -> None:
        if feito.done():
            return
        if erro is None:
            feito.set_result(resultado)
        else:
            feito.set_exception(erro)

    def correr() -> None:
        resultado: Any = None
        erro: BaseException | None = RuntimeError(f"{trabalho!r} caiu")
        try:
            resultado, erro = trabalho(*args), None
        finally:
            with contextlib.suppress(RuntimeError):
                laco.call_soon_threadsafe(entregar, resultado, erro)

    threading.Thread(target=correr, name="imersao-rede", daemon=True).start()
    return await feito


class Extensao:
    """A porta, o motor da receita e a saída, juntos."""

    def __init__(self, porta: Porta, receita: Receita | Escolhida,
                 biblioteca: Biblioteca | None = None, dados: Path | None = None,
                 comunidade: Comunidade | None = None) -> None:
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
        self.do_estudio: set[str] = set()
        self.estudio = Estudio(porta.pedir, dados / "receitas" if dados else None, ler_receita)
        self.montador = Montador(dados / "receitas" if dados else None, ler_receita,
                                 lambda: (self.jogo, self.receita.dados), lambda: self.motor.opcoes)
        self.editor = Editor(dados / "receitas" if dados else None,
                             lambda: (self.jogo, self.receita.dados))
        self.gravador = Gravador()
        self.tocando: asyncio.Task[None] | None = None
        self.parar_de_tocar = asyncio.Event()
        self.comunidade = comunidade
        self.procurando: asyncio.Task[dict[str, Any]] | None = None
        self.memoria_vale = True
        self.controles: list[dict[str, Any]] = []
        self.calados = ajustes.controles_calados(dados)
        self.ultimo_estado: dict[str, Any] | None = None

    @property
    def escolha(self) -> str:
        valor = self.opcoes.get(OPCAO_DA_RECEITA, PELO_JOGO)
        return valor if isinstance(valor, str) else PELO_JOGO

    async def assinar(self) -> None:
        """Assina o que a receita de agora lê e ainda não estava assinado, e solta o tópico cuja
        chave a janela desligou."""
        faltam = [t for t in topicos_assinados(self.receita, self.opcoes)
                  if t not in self.assinados]
        if faltam:
            await self.porta.pedir("eventos.assinar", {"topicos": faltam})
            self.assinados |= set(faltam)
        sobram = sorted(t for t in self.assinados - self.do_estudio
                        if not ajustes.topico_ligado(t, self.opcoes))
        if sobram:
            await self.porta.pedir("eventos.desassinar", {"topicos": sobram})
            self.assinados -= set(sobram)

    async def assinar_o_estudio(self, topicos: tuple[str, ...] = TOPICOS_DO_ESTUDIO) -> None:
        """O Estúdio ouve o som do jogo e o botão do meio enquanto caça, e o que grava."""
        for topico in topicos:
            if topico in self.assinados:
                continue
            with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
                await self.porta.pedir("eventos.assinar", {"topicos": [topico]})
                self.assinados.add(topico)
                self.do_estudio.add(topico)

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

    async def ao_estudio(self, topico: str, nome: Any, dados: dict[str, Any],
                         uniq: Any = None) -> None:
        """Os eventos que o Estúdio usa; a falha de um pedido para a caça e responde à página,
        sem calar a porta para o resto da extensão."""
        try:
            await self._ao_estudio(topico, nome, dados, uniq, time.monotonic() * 1000.0)
        except FALHAS_DO_ESTUDIO as exc:
            diario(f"o Estúdio parou: {exc}")
            self.estudio.cancelar()
            pedido = dados.get("id") if topico == "extensao.mensagem" else None
            await self.responder_ao_estudio({"tipo": "erro", "frase": FRASE_DA_FALHA}, pedido)

    async def _ao_estudio(self, topico: str, nome: Any, dados: dict[str, Any],
                          uniq: Any, agora_ms: float) -> None:
        if topico == "extensao.mensagem":
            pedido = dados.get("dados", dados)
            if isinstance(pedido, dict):
                tipo = pedido.get("tipo")
                if tipo in TIPOS_DO_MONTADOR:
                    resposta = self.montador.mensagem(pedido)
                elif tipo in TIPOS_DO_EDITOR:
                    resposta = self.editor.mensagem(pedido)
                elif tipo in TIPOS_DA_COMUNIDADE:
                    resposta = await self.ao_comunidade(str(tipo), pedido)
                elif tipo in TIPOS_DO_GRAVADOR:
                    resposta = await self.ao_gravador(str(tipo), agora_ms)
                else:
                    if tipo == "comecar":
                        await self.assinar_o_estudio()
                    resposta = await self.estudio.mensagem(pedido, agora_ms)
                if resposta.get("tipo") in RESPOSTAS_QUE_GRAVAM:
                    await self.reler_as_opcoes()
                await self.responder_ao_estudio(resposta, dados.get("id"))
        if self.gravador.gravando and isinstance(nome, str):
            self.gravador.ouvir(topico, nome, uniq if isinstance(uniq, str) else None, dados,
                                agora_ms)
        if topico == "jogo.som":
            self.estudio.ouvir(dados, agora_ms)
        elif (topico == "botoes" and nome == "button.down" and self.estudio.ativo
              and BOTAO_DA_MARCA in (dados.get("botao"), dados.get("button"))):
            await self.responder_ao_estudio(await self.estudio.marca(agora_ms))

    async def ao_gravador(self, tipo: str, agora_ms: float) -> dict[str, Any]:
        """«Gravar», «Parar» e «Tocar» da linha do tempo."""
        if tipo == "gravar":
            await self.assinar_o_estudio(linha_do_tempo.TOPICOS_GRAVADOS)
            self.gravador.gravar(agora_ms)
            return {"tipo": "gravando", "segundos": linha_do_tempo.DURACAO_MS / 1000}
        if tipo == "parar":
            self.parar_de_tocar.set()
            if not self.gravador.gravando:
                return {"tipo": "parado"}
            gravada = self.gravador.parar()
            if self.dados is not None and self.jogo is not None:
                with contextlib.suppress(OSError):
                    linha_do_tempo.gravar_no_disco(self.dados, self.jogo, gravada)
            return {"tipo": "gravado", "marcos": len(gravada.marcos),
                    "segundos": round(gravada.duracao_ms / 1000, 1)}
        linha = self.gravador.linha if self.gravador.linha.marcos else (
            linha_do_tempo.ler_do_disco(self.dados, self.jogo)
            if self.dados is not None and self.jogo is not None else None)
        if linha is None or not linha.marcos:
            return {"tipo": "erro", "frase": "grave antes de tocar"}
        if self.tocando is not None and not self.tocando.done():
            self.parar_de_tocar.set()
            await asyncio.gather(self.tocando, return_exceptions=True)
        self.parar_de_tocar = asyncio.Event()
        self.tocando = asyncio.create_task(self._tocar_ate_o_fim(linha, self.parar_de_tocar))
        return {"tipo": "tocando", "segundos": round(linha.duracao_ms / 1000, 1)}

    async def _tocar_ate_o_fim(self, linha: linha_do_tempo.LinhaDoTempo,
                               parar: asyncio.Event) -> None:
        """Toca a linha e, no fim dela, a página volta a mostrar a linha parada."""
        await linha_do_tempo.tocar(linha, self.motor.evento, parar)
        if not parar.is_set():
            await self.responder_ao_estudio({"tipo": "tocado",
                                             "segundos": round(linha.duracao_ms / 1000, 1)})

    async def procurar(self, agora: bool = False) -> dict[str, Any]:
        """A receita da comunidade do jogo aberto; a nova vale no tique seguinte."""
        if self.comunidade is None:
            return {"tipo": "erro", "frase": "sem a pasta de dados da extensão"}
        resultado = await em_fio_solto(self.comunidade.procurar, self.jogo, agora)
        if resultado.get("tipo") != "procurado":
            diario(f"as receitas da comunidade não vieram: "
                   f"{resultado.get('detalhe') or resultado.get('frase')}")
        await self.escolher()
        resultado.pop("detalhe", None)
        return {**resultado, "origem": self.escolhida.rotulo}

    def procurar_em_fundo(self, agora: bool = False) -> None:
        if self.comunidade is not None and (self.procurando is None or self.procurando.done()):
            self.procurando = asyncio.create_task(self.procurar(agora))

    async def ao_comunidade(self, tipo: str, pedido: dict[str, Any]) -> dict[str, Any]:
        """«Procurar receitas» e a chave «Memória» da receita da comunidade."""
        if tipo == "procurar":
            return await self.procurar(agora=True)
        if self.comunidade is None:
            return {"tipo": "erro", "frase": "sem a pasta de dados da extensão"}
        resposta = self.comunidade.ligar_a_memoria(self.jogo, pedido.get("ligar") is True,
                                                   pedido.get("confirmado") is True)
        self.memoria_vale = self._memoria_vale()
        return resposta

    def _memoria_vale(self) -> bool:
        return self.escolhida.origem != "comunidade" or (
            self.comunidade is not None and self.comunidade.memoria_ligada(self.jogo))

    def _estado(self) -> dict[str, Any]:
        return {"ligado": True, "nivel": self.motor.clima(), "perfil": self.escolhida.rotulo,
                "aparelhos": self.aparelhos(), "conexoes": []}  # (noqa-acento)

    async def publicar_o_estado(self) -> None:
        """A coluna «Agora» da janela: de onde veio a receita que vale e o clima da cena, no
        nível; os controles conectados vão como aparelhos, cada um com a chave «Sente os
        efeitos» na aba Geral."""
        estado = self._estado()
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.porta.pedir("acessorios.estado", estado)
            self.ultimo_estado = estado

    async def publicar_se_mudou(self) -> None:
        """O clima ou os controles mudaram depois do último estado publicado."""
        if self.ultimo_estado is not None and self._estado() != self.ultimo_estado:
            await self.publicar_o_estado()

    def _por_id(self) -> list[tuple[str, dict[str, Any]]]:
        return [(ajustes.id_do_controle(c.get("jogador"), n), c)
                for n, c in enumerate(self.controles, 1)]

    def aparelhos(self) -> list[dict[str, Any]]:
        """Um cartão por controle conectado, com a chave de sentir; o ``id`` nunca é o
        ``uniq``."""
        return [{"id": ident, "nome": ajustes.nome_do_controle(c, n),
                 "ligado": ident not in self.calados}
                for n, (ident, c) in enumerate(self._por_id(), 1)]

    def _calar(self) -> None:
        self.motor.calar({c["uniq"] for ident, c in self._por_id() if ident in self.calados})

    async def sentir(self, alvo: Any, valor: Any) -> None:
        """A chave de um controle na aba Geral: desligada, nenhum efeito chega a ele."""
        if not isinstance(alvo, str) or not isinstance(valor, bool):
            return
        calados = ajustes.sentir(self.calados, alvo, valor)
        if calados != self.calados:
            self.calados = calados
            if self.dados is not None:
                with contextlib.suppress(OSError):
                    ajustes.guardar_os_controles(self.dados, calados)
            self._calar()
        await self.publicar_se_mudou()

    async def escolher(self) -> None:
        """A receita do jogo de agora; quando muda, o motor a troca no tique seguinte."""
        if self.biblioteca is None:
            return
        nova = self.biblioteca.para(self.jogo, self.escolha)
        if nova.marca == self.escolhida.marca and nova.receita.dados == self.receita.dados:
            self.memoria_vale = self._memoria_vale()
            return
        self.escolhida, self.receita = nova, nova.receita
        self.memoria_vale = self._memoria_vale()
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
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.assinar()

    async def atualizar_os_controles(self) -> None:
        resposta = await self.porta.pedir("controles.lista", {})
        lista = resposta.get("controles", [])
        self.controles = [c for c in (lista if isinstance(lista, list) else [])
                          if isinstance(c, dict) and isinstance(c.get("uniq"), str)]
        self.motor.controles(self.controles)
        self._calar()
        await self.publicar_se_mudou()

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
            if self.jogo is not None:
                self.procurar_em_fundo()
        elif topico == "extensao.opcao" and isinstance(dados, dict):
            ident, valor = dados.get("id"), dados.get("valor")
            if isinstance(ident, str) and isinstance(valor, (bool, int, float, str)):
                self.motor.opcoes[ident] = valor
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") == ACAO_DE_PROCURAR):  # (noqa-acento)
            self.procurar_em_fundo(agora=True)
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") == ajustes.ACAO_DE_LIGAR):  # (noqa-acento)
            await self.sentir(dados.get("alvo"), dados.get("valor"))
        if isinstance(topico, str) and isinstance(dados, dict):
            await self.ao_estudio(topico, nome, dados, params.get("uniq"))
        if topico == "jogo.memoria" and not self.memoria_vale:
            return True
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
                                               PELO_JOGO), biblioteca, dados,
                        Comunidade(dados) if dados is not None else None)
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

    async def acompanhar_o_clima() -> None:
        while True:
            await asyncio.sleep(PUBLICA_O_CLIMA_S)
            await extensao.publicar_se_mudou()

    ouvir = asyncio.create_task(ouvir_a_porta())
    vigiar = asyncio.create_task(vigiar_as_opcoes())
    clima = asyncio.create_task(acompanhar_o_clima())
    motor = asyncio.create_task(rodar_o_laco(extensao.motor, extensao.saida, fim))
    try:
        await fim.wait()
        with contextlib.suppress(ConnectionError, asyncio.TimeoutError, RuntimeError):
            await asyncio.wait_for(motor, 2.0)
    finally:
        extensao.parar_de_tocar.set()
        tarefas = [ouvir, vigiar, clima, motor, *([extensao.tocando] if extensao.tocando else []),
                   *([extensao.procurando] if extensao.procurando else [])]
        for tarefa in tarefas:
            tarefa.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
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
