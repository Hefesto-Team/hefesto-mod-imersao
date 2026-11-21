"""O processo que o Hefesto abre para o Modo imersão: a receita, o motor e a porta.

Fala com o Hefesto pela porta das modificações (``mod.ola``, ``controles.lista``,
``eventos.assinar``, ``acessorios.estado`` e as escritas da :class:`~motor.saida.Saida`). A
receita se escolhe pelo jogo aberto (``perfil.jogo``), na
:class:`~receita.biblioteca.Biblioteca`: a de quem joga, a estudada, a da comunidade e, sem
nenhuma, o universal (``receitas/universal.json``); a recusa vai ao diário com a linha de cada erro.
A troca vale no tique seguinte, e o que a receita velha escrevia volta ao jogo. As opções da janela
moram em ``$HEFESTO_MOD_DADOS/opcoes.json``: a opção ``receita`` (pelo jogo, ou o universal
sempre) e as entradas das receitas, relidas a cada mudança do arquivo e, no arrastar, pelo
``extensao.opcao``. A faixa do alto da janela diz a ``situacao`` (tocando, com o nome do jogo;
calado, com o motivo; esperando um jogo) e, nas linhas, o estilo, o ajuste que vale, quem sente e a
tensão da cena em palavras no Terror; as ``leituras`` dizem o que cada sentido lê, ao lado da chave
dele; os ``presentes`` (as entradas e os canais da receita que vale) escondem o cartão do efeito que
ela não tem. Cada controle conectado é um cartão na aba Controles, e o desligado não recebe efeito;
o cartão leva, lado a lado,
a Força e o volume daquele controle, que valem juntos e vezes a Força geral
(``controles.json``). Além do que a receita lê, assina o que o jogo escreve nos canais em que ela escreve, para o motor medir o caminho
do controle e a máscara do lançamento (``jogo.identidade``). Os sentidos e os canais desligados na
janela (``opcoes.py``) desassinam o tópico deles e calam o que escrevem. A tela só se lê no clique
«Ver a tela» da aba Sentir: ele pede ``tela.ver`` e assina ``jogo.tela``, até «Parar de ver», o
segundo clique, o jogo que fecha ou a saída da extensão (``tela.parar``); o Hefesto que não conhece
``tela.ver`` vira a linha «Tela» da faixa, e nada se assina.
A :class:`~comunidade.Comunidade` procura a receita do jogo aberto no índice assinado a cada jogo
que abre (o índice se baixa uma vez por dia). A cada minuto em que houve jogo, uma linha do diário conta,
por controle e pela cor do plástico, o que tocou em cada canal e por que algo não tocou
(:class:`~motor.conta.ContaDoMinuto`). A porta lê a cor em fundo, depois da conexão, e a renomeia
sem evento: a lista dos controles se pede de novo a cada :data:`RELE_OS_CONTROLES_S` enquanto um
controle está sem cor, e sempre antes da linha do minuto. O ``jogo.memoria`` só chega ao motor
com a chave «Memória neste jogo» do Hefesto ligada, que o ``perfil.trocou`` traz em ``memoria``.
Os botões de testar de cada cartão da aba Efeitos declaram ``responde``: a extensão devolve à janela,
em até :data:`ESPERA_O_TESTE_S`, uma linha por controle, ``{controles: [{uniq, nome, tocou,
motivo}]}``, com o nome do plástico, a
frase da recusa da porta ou o motivo da extensão em palavras (:class:`Teste`).
O Som no corpo e os Gatilhos que vibram tocam em todo estilo e com toda receita: cada controle que
sente recebe o ``corpo.ligar`` (:meth:`Extensao.pedidos_do_corpo`), renovado pela saída enquanto a
extensão vive, e a linha do minuto conta cada pedido aceito e cada recusa.
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
from comunidade import Comunidade  # noqa: E402
from motor.arbitragem import Pedido, Vaga  # noqa: E402
from motor.caminho import CANAIS as CANAIS_DO_JOGO  # noqa: E402
from motor.conta import ContaDoMinuto  # noqa: E402
from motor.laco import REGRA_DO_TESTE, Motor  # noqa: E402
from motor.laco import rodar as rodar_o_laco  # noqa: E402
from motor.saida import Saida  # noqa: E402
from receita import estilos  # noqa: E402
from receita.biblioteca import (  # noqa: E402
    ARQUIVO_DE_ANTES,
    PELO_JOGO,
    UNIVERSAL_SEMPRE,
    Biblioteca,
    Escolhida,
)
from receita.formato import CANAIS as CANAIS_DA_RECEITA  # noqa: E402
from receita.formato import Receita, ReceitaRecusada, ler_receita, receita_vazia  # noqa: E402

ARQUIVO_DA_RECEITA = ARQUIVO_DE_ANTES
ARQUIVO_DO_UNIVERSAL = AQUI / "receitas" / "universal.json"
PASTA_DAS_ESTUDADAS = AQUI / "receitas" / "estudadas"
ARQUIVO_DAS_OPCOES = ajustes.ARQUIVO_DAS_OPCOES
OPCAO_DA_RECEITA = "receita"
RELE_AS_OPCOES_S = 0.5
RESUMO_A_CADA_S = 60.0
RELE_OS_CONTROLES_S = 5.0
PUBLICA_O_CLIMA_S = 0.5
TOPICOS_DA_PORTA = (
    "conexao", "perfil.jogo", "jogo.vibracao", "jogo.gatilho", "jogo.haptica", "entradas",  # (noqa-acento)
    "botoes", "movimento", "jogo.som", "microfone.nivel", "jogo.tela", "jogo.identidade",
    "jogo.memoria", "jogo.estilo",
)
TETO_DAS_LINHAS = 6
TETO_DO_ROTULO = 20
TETO_DO_VALOR = 40
TETO_DOS_PRESENTES = 32
PREFIXO_DO_CANAL = "canal."
NOMES_DOS_SENTIDOS = (
    (("sentido.som", "jogo.som"), "som"),
    (("sentido.rumble", "jogo.vibracao"), "vibração"),
    (("jogo.haptica",), "vibração fina"),
    (("sentido.microfone", "microfone.nivel"), "microfone"),
    (("sentido.quietude",), "parado"),
    (("movimento",), "movimento"),
    (("sentido.tela", "jogo.tela"), "tela"),
    (("sentido.golpe",), "golpe"),
    (("entradas", "botoes"), "botões"),
    (("jogo.gatilho",), "gatilhos"),
    (("jogo.memoria",), "memória"),
)
ROTULOS_DOS_CANAIS = {
    "haptica": "Vibração fina", "motor": "Motores", "gatilho": "Gatilhos", "luz": "Barra de luz",
    "leds": "Luzes de jogador", "som": "Alto-falante", "mira": "Peso da mira",
}
ESPERA_A_MEMORIA = "Desligada"
TELA_VENDO = "Vendo"
TELA_SEM_O_PEDIDO = "Este Hefesto não lê"
TELA_RECUSADA = "Recusada"
METODO_DESCONHECIDO = -32601
ESPERA_O_FIM_DA_TELA_S = 1.0
ESPERA_O_TESTE_S = 0.7
TETO_DO_MOTIVO = 120
ESCRITAS_DO_CANAL = {
    "motor": frozenset({"vibracao"}), "haptica": frozenset({"haptica", "vibracao"}),
    "gatilho": frozenset({"gatilho"}), "som": frozenset({"som"}), "luz": frozenset({"luz"}),
    "leds": frozenset({"leds"}), "mira": frozenset({"mira"}),
}
RECUSA_RECENTE_S = 5.0
CALADO_SEM_INTENSIDADE = "A intensidade está em zero"
CALADO_SEM_QUEM_SINTA = "Nenhum controle sente os efeitos"
CALADO_SEM_CONTROLE = "Nenhum controle conectado"
TETO_DA_FRASE = 120
LEITURA_NAO_USA = "Este ajuste não usa"
LEITURA_FORA = "Este Hefesto não entrega"
PASSO_DO_MEDIDOR = 5
MEIA_VIDA_DA_LEITURA_S = 0.6
FONTES_DA_LEITURA: dict[str, tuple[str, ...]] = {
    "sentido_som": ("jogo.som",), "sentido_vibracao": ("jogo.vibracao", "jogo.haptica"),
    "sentido_microfone": ("microfone.nivel",), "sentido_golpe": ("entradas",),
    "sentido_parado": (),
}
OPCAO_DO_SENTIDO = {"som": "sentido_som", "vibração": "sentido_vibracao",
                    "vibração fina": "sentido_vibracao", "microfone": "sentido_microfone",
                    "parado": "sentido_parado", "golpe": "sentido_golpe"}
TENSOES = ("Calma", "Atenta", "Tensa", "Pânico")
MOTIVO_CALADO = "o controle está desligado na extensão"
MOTIVO_SEM_O_EFEITO = "a receita de agora não tem este efeito"
MOTIVO_DESLIGADO = "o efeito está desligado na janela"
MOTIVO_SEM_FORCA = "a força deste controle está em zero"
MOTIVO_CEDEU = "o jogo vibra mais forte neste controle agora"
MOTIVO_NAO_CHEGOU = "o efeito não chegou a este controle"
MOTIVO_TETO = "o teto de efeitos deste controle está cheio"
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
    """Os tópicos da receita e sempre o ``perfil.jogo`` e o ``jogo.estilo``: eles dizem qual
    receita e qual preset valem."""
    pedidos = set(topicos_da_receita(receita)) | {"perfil.jogo", "jogo.estilo"}
    return [t for t in TOPICOS_DA_PORTA if t in pedidos and ajustes.topico_ligado(t, opcoes)]


def presentes_da_receita(receita: Receita) -> list[str]:
    """O que a receita tem, para o ``@presente`` da janela: as entradas dela e os canais em que
    escreve (``canal.<nome>``), até o teto da porta."""
    canais = {e["canal"] for e in receita.secao("efeitos").values()}
    nomes = [*receita.secao("entradas"),
             *(f"{PREFIXO_DO_CANAL}{c}" for c in CANAIS_DA_RECEITA if c in canais)]
    return [n for n in dict.fromkeys(nomes) if n.strip() and len(n) <= 40][:TETO_DOS_PRESENTES]


def nome_do_sentido(de: str) -> str | None:
    return next((nome for topicos, nome in NOMES_DOS_SENTIDOS if de in topicos), None)


def lista_curta(nomes: list[str], teto: int = TETO_DO_VALOR) -> str:
    """Os nomes numa linha de até ``teto`` letras; o que não cabe vira ``+N`` no fim."""
    for cabem in range(len(nomes), -1, -1):
        resto = len(nomes) - cabem
        texto = ", ".join([*nomes[:cabem], *([f"+{resto}"] if resto else [])])
        if len(texto) <= teto:
            return texto[:1].upper() + texto[1:]
    return f"+{len(nomes)}"


def escolha_da_receita(opcoes: dict[str, Any]) -> str:
    """A escolha da biblioteca pelo «Ajuste» da janela: o universal sempre, ou pelo jogo."""
    return UNIVERSAL_SEMPRE if ajustes.sempre_o_universal(opcoes) else PELO_JOGO


def tensao_da_cena(clima: int, limiar: int) -> str:
    """A tensão da cena em palavras, pelo clima de 0 a 10 e o limiar em que ela fica tensa: Calma
    abaixo da metade do limiar, Atenta até ele, Tensa dele em diante e Pânico no topo."""
    if clima < limiar / 2:
        return TENSOES[0]
    if clima < limiar:
        return TENSOES[1]
    return TENSOES[3] if clima >= max(limiar + 3, 9) else TENSOES[2]


def _fracao(valor: Any, escala: float = 1.0) -> float | None:
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return min(1.0, max(0.0, float(valor) / escala))


def intensidade_do_evento(topico: str, dados: dict[str, Any]) -> float | None:
    """O quanto um evento da porta traz agora, de 0 a 1: a energia do estalo do som, o nível do
    microfone (zero no mudo), a vibração ou a háptica que o jogo pede e o gatilho apertado."""
    if topico == "jogo.som":
        return _fracao(dados.get("energia"))
    if topico == "microfone.nivel":
        return 0.0 if dados.get("mudo") is True else _fracao(dados.get("nivel"))
    if topico == "jogo.vibracao":
        pares = [_fracao(v, 255) for v in dados.get("pedido") or ()]
        return max((v for v in pares if v is not None), default=None)
    if topico == "jogo.haptica":
        lados = [_fracao(v) for v in dados.get("intensidade") or ()]
        return max((v for v in lados if v is not None), default=None)
    if topico == "entradas":
        gatilhos = [_fracao(dados.get(g), 255) for g in ("l2", "r2")]
        return max((v for v in gatilhos if v is not None), default=None)
    return None


def com_maiuscula(frase: str) -> str:
    return frase[:1].upper() + frase[1:]


def nome_do_efeito(receita: Receita, efeito: str) -> str:
    """O rótulo da entrada de mesmo nome do efeito; sem ela, o do canal em que ele escreve."""
    entrada = receita.secao("entradas").get(efeito, {})
    rotulo = entrada.get("rotulo") if isinstance(entrada, dict) else None
    if isinstance(rotulo, str) and rotulo.strip():
        return rotulo.strip()
    canal = receita.secao("efeitos").get(efeito, {}).get("canal")
    return ROTULOS_DOS_CANAIS.get(str(canal), efeito)


class Teste:
    """O veredito de um clique de testar, controle a controle: tocou quando a porta aceitou a
    escrita do efeito testado, e não tocou com a frase da recusa dela ou o motivo da extensão."""

    def __init__(self, efeitos: set[str], canais: set[str], alvos: list[str],
                 nomes: dict[str, str] | None = None) -> None:
        self.nomes = dict(nomes or {})
        self.efeitos = frozenset(efeitos)
        self.escritas = frozenset().union(*(ESCRITAS_DO_CANAL.get(c, frozenset({c}))
                                            for c in canais))
        self.alvos = list(dict.fromkeys(alvos))
        self.veredito: dict[str, tuple[bool, str | None]] = {}
        self.vistos: set[str] = set()
        self.adiados: set[str] = set()
        self.com_pedido: set[str] = set()
        self.tiques = 0
        self.pronto = asyncio.Event()

    def decidir(self, uniq: str, tocou: bool, motivo: str | None = None) -> None:
        if uniq in self.alvos and uniq not in self.veredito:
            self.veredito[uniq] = (tocou, None if tocou else (motivo or "")[:TETO_DO_MOTIVO])
        if all(u in self.veredito for u in self.alvos):
            self.pronto.set()

    def _do_teste(self, pedidos: dict[Vaga, Pedido], uniq: str) -> bool:
        return any(p.uniq == uniq and p.regra == REGRA_DO_TESTE and p.efeito in self.efeitos
                   and p.forca > 0 for p in pedidos.values())

    def ver(self, vencedores: dict[Vaga, Pedido], cedidos: dict[Vaga, Pedido],
            aceitas: list[tuple[str, str]], frases: list[tuple[str, str, str]],
            adiadas: list[tuple[str, str]]) -> None:
        """Um tique da saída: o efeito testado que venceu e foi escrito, recusado ou adiado pelo
        teto da extensão."""
        self.tiques += 1
        for uniq in [u for u in self.alvos if u not in self.veredito]:
            if self._do_teste(cedidos, uniq) or self._do_teste(vencedores, uniq):
                self.com_pedido.add(uniq)
            if self._do_teste(cedidos, uniq) and not self._do_teste(vencedores, uniq):
                self.decidir(uniq, False, MOTIVO_CEDEU)
                continue
            if not self._do_teste(vencedores, uniq):
                continue
            frase = next((f for u, c, f in frases if u == uniq and c in self.escritas), None)
            if frase is not None:
                self.decidir(uniq, False, frase)
            elif any(u == uniq and c in self.escritas for u, c in aceitas):
                self.decidir(uniq, True)
            elif any(u == uniq and c in self.escritas for u, c in adiadas):
                self.adiados.add(uniq)
            else:
                self.vistos.add(uniq)

    def fechar(self) -> list[dict[str, Any]]:
        """A resposta: o efeito que venceu sem recusa e sem adiar está no controle, mesmo sem
        escrita nova; o que o teto da extensão adiou e não saiu não tocou, e o efeito que o laço
        não pediu a este controle em tique nenhum está em zero na janela."""
        for uniq in self.alvos:
            motivo = (MOTIVO_TETO if uniq in self.adiados
                      else MOTIVO_DESLIGADO if self.tiques and uniq not in self.com_pedido
                      else MOTIVO_NAO_CHEGOU)
            self.decidir(uniq, uniq in self.vistos and uniq not in self.adiados, motivo)
        return [{"uniq": u, **({"nome": self.nomes[u]} if u in self.nomes else {}),
                 "tocou": self.veredito[u][0], "motivo": self.veredito[u][1]}
                for u in self.alvos]


class SaidaQueAnota(Saida):
    """A :class:`~motor.saida.Saida` que conta à extensão o que vence em cada tique."""

    def __init__(self, *args: Any, anotar: Callable[[dict[Vaga, Pedido]], None],
                 contar: Callable[[dict[Vaga, Pedido]], None] | None = None,
                 **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._anotar = anotar
        self._contar = contar or (lambda _vencedores: None)

    async def aplicar(self, t_ms: float, vencedores: dict[Vaga, Pedido]) -> None:
        self._anotar(vencedores)
        await super().aplicar(t_ms, vencedores)
        self._contar(vencedores)


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
        self.vendo = False
        self.tela: str | None = None
        self.opcoes = ajustes.com_a_tela(ler_as_opcoes(dados), self.vendo)
        self.motor = Motor(self.receita, self.opcoes)
        self.saida = SaidaQueAnota(porta.pedir, diario, self.motor.recusado,
                                   self.motor.pelo_motor, anotar=self.anotar,
                                   contar=self.contar)
        self.conta = ContaDoMinuto()
        self.assinados: set[str] = set()
        self.comunidade = comunidade
        self.procurando: asyncio.Task[dict[str, Any]] | None = None
        self.memoria_vale = False
        self.relogio: Callable[[], float] = time.time
        self.ultimo_efeito: tuple[str, float] | None = None
        self._inicio_do_ultimo = float("-inf")
        self.controles: list[dict[str, Any]] = []
        self.calados = ajustes.controles_calados(dados)
        self.niveis = ajustes.niveis_dos_controles(dados)
        self.ultimo_estado: dict[str, Any] | None = None
        self.estilo_do_jogo: str | None = None
        self.estilo_dito = False
        self.preset: str | None = None
        self.aplicar_o_estilo()
        self.saida.pedidos_do_corpo = self.pedidos_do_corpo
        self.testes: list[Teste] = []
        self.respondendo: set[asyncio.Task[None]] = set()
        self.em_cena = False
        self.nome_do_jogo: str | None = None
        self.recusado_em: dict[str, tuple[str, float]] = {}
        self.tocou_em: dict[str, float] = {}
        self.ouvido: dict[str, tuple[float, float]] = {}

    @property
    def escolha(self) -> str:
        return escolha_da_receita(self.opcoes)

    async def assinar(self) -> None:
        """Assina o que a receita de agora lê e ainda não estava assinado, e solta o tópico cuja
        chave a janela desligou."""
        querem = topicos_assinados(self.receita, self.opcoes)
        if self.vendo and ajustes.TOPICO_DA_TELA not in querem:
            querem.append(ajustes.TOPICO_DA_TELA)
        faltam = [t for t in querem if t not in self.assinados]
        if faltam:
            await self.porta.pedir("eventos.assinar", {"topicos": faltam})
            self.assinados |= set(faltam)
        sobram = sorted(t for t in self.assinados if not ajustes.topico_ligado(t, self.opcoes))
        if sobram:
            await self.porta.pedir("eventos.desassinar", {"topicos": sobram})
            self.assinados -= set(sobram)

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
        if resultado.get("memoria"):
            resultado["memoria_ligada"] = self.memoria_vale
        return {**resultado, "origem": self.escolhida.rotulo}

    def procurar_em_fundo(self, agora: bool = False) -> None:
        if self.comunidade is not None and (self.procurando is None or self.procurando.done()):
            self.procurando = asyncio.create_task(self.procurar(agora))

    def anotar(self, vencedores: dict[Vaga, Pedido]) -> None:
        """O último efeito que começou a tocar, com a hora em que começou."""
        tocando = [p for p in vencedores.values() if p.forca > 0]
        if not tocando:
            return
        novo = max(tocando, key=lambda p: p.inicio_ms)
        if novo.inicio_ms > self._inicio_do_ultimo:
            self._inicio_do_ultimo = novo.inicio_ms
            self.ultimo_efeito = (nome_do_efeito(self.receita, novo.efeito), self.relogio())

    def contar(self, vencedores: dict[Vaga, Pedido]) -> None:
        """A conta do minuto, a cada tique da saída: o que tocou e o que não tocou, e por quê."""
        aceitas, frases, adiadas = self.saida.tirar_os_desfechos()
        agora = self.relogio()
        for uniq, _canal in aceitas:
            self.tocou_em[uniq] = agora
        for uniq, _canal, frase in frases:
            self.recusado_em[uniq] = (frase, agora)
        for teste in self.testes:
            teste.ver(vencedores, self.motor.cedidos, aceitas, frases, adiadas)
        self.conta.tique(vencedores, self.motor.cedidos, self.saida.tirar_as_recusas(),
                         self.jogo is not None)
        for uniq, parte in self.saida.tirar_os_corpos():
            self.conta.tocados[(uniq, parte)] += 1
            self.tocou_em[uniq] = agora

    def pedidos_do_corpo(self) -> dict[str, dict[str, Any]]:
        """O ``corpo.ligar`` de cada controle conectado que sente, pela Força dele e pelas opções
        de agora; o preset do estilo não cala nenhum dos dois."""
        pedidos: dict[str, dict[str, Any]] = {}
        for ident, controle in self._por_id():
            if ident in self.calados:
                continue
            forca = ajustes.nivel(self.niveis, ajustes.CONTROLE_DA_FORCA, ident) / 100
            if pedido := ajustes.pedido_do_corpo(self.motor.opcoes, forca,
                                                 self.motor.sem_do_estilo):
                pedidos[controle["uniq"]] = pedido
        return pedidos

    def presentes(self) -> list[str]:
        """Os ``presentes`` do estado: o Som no corpo e os Gatilhos que vibram, que tocam em todo
        estilo, e o que a receita de agora tem."""
        corpo = [n for n in (ajustes.SOM_NO_CORPO, ajustes.GATILHOS_QUE_VIBRAM)
                 if n not in self.motor.sem_do_estilo]
        nomes = [*corpo, *presentes_da_receita(self.receita)]
        return list(dict.fromkeys(nomes))[:TETO_DOS_PRESENTES]

    def fechar_o_minuto(self) -> None:
        """O resumo do minuto que acabou vai ao diário, só se houve jogo nele."""
        nomes = {c["uniq"]: ajustes.nome_do_controle(c, n)
                 for n, c in enumerate(self.controles, 1)}
        hora = time.strftime("%H:%M", time.localtime(self.relogio()))
        if (linha := self.conta.fechar(hora, nomes)) is not None:
            diario(linha)

    def _le_a_memoria(self) -> bool:
        return any(s["de"] == "jogo.memoria" for s in self.receita.secao("sentidos").values())

    def sentidos_lendo(self) -> list[str]:
        """Os sentidos da receita que valem agora: a chave ligada, o tópico assinado e, na
        memória, a chave «Memória neste jogo» ligada."""
        calados = ajustes.topicos_calados(self.opcoes)
        lendo: set[str] = set()
        for sentido in self.receita.secao("sentidos").values():
            de = sentido["de"]
            nome = nome_do_sentido(de)
            if (nome is None or de in calados
                    or not universais.origens([de]) & self.assinados
                    or (de == "jogo.memoria" and not self.memoria_vale)):
                continue
            lendo.add(nome)
        return [nome for _, nome in NOMES_DOS_SENTIDOS if nome in lendo]

    def _sentem(self) -> list[tuple[str, str]]:
        """Os controles conectados que sentem, ``(nome, uniq)``."""
        return [(ajustes.nome_do_controle(c, n), c["uniq"])
                for n, (ident, c) in enumerate(self._por_id(), 1) if ident not in self.calados]

    def _recusa_de_agora(self, uniq: str) -> str | None:
        """A frase da porta da última recusa ao controle, quando ela é recente e nada tocou nele
        depois."""
        recusa = self.recusado_em.get(uniq)
        if recusa is None:
            return None
        frase, quando = recusa
        recente = self.relogio() - quando <= RECUSA_RECENTE_S
        return frase if recente and self.tocou_em.get(uniq, float("-inf")) < quando else None

    def situacao(self) -> dict[str, Any]:
        """A faixa do alto da janela: esperando um jogo, calado com o motivo (a intensidade em
        zero, nenhum controle que sente, ou a porta recusando cada um deles) ou tocando, com o
        nome do jogo."""
        if not self.em_cena and self.jogo is None:
            return {"estado": "esperando", "frase": None}
        calado = None
        sentem = self._sentem()
        recusas = [(nome, frase) for nome, uniq in sentem
                   if (frase := self._recusa_de_agora(uniq)) is not None]
        if ajustes.forca(self.motor.opcoes) <= 0:
            calado = CALADO_SEM_INTENSIDADE
        elif not self.controles:
            calado = CALADO_SEM_CONTROLE
        elif not sentem:
            calado = CALADO_SEM_QUEM_SINTA
        elif len(recusas) == len(sentem):
            frases = list(dict.fromkeys(f for _n, f in recusas))
            calado = (com_maiuscula(frases[0]) if len(frases) == 1
                      else f"{recusas[0][0]}: {recusas[0][1]}")
        if calado is not None:
            return {"estado": "calado", "frase": calado[:TETO_DA_FRASE]}
        nome = (self.nome_do_jogo or "")[:TETO_DA_FRASE]
        return {"estado": "tocando", "frase": nome or None}

    def leituras(self) -> list[dict[str, Any]]:
        """O que cada sentido lê agora, de 0 a 100, ao lado da chave dele na janela: zero com a
        chave desligada, e cego com a frase quando o ajuste de agora não o usa ou o Hefesto não
        entrega o que ele lê."""
        sentidos = self.receita.secao("sentidos")
        lendo = set(self.sentidos_lendo())
        saida: list[dict[str, Any]] = []
        for ident, (_topicos, padrao) in ajustes.SENTIDOS.items():
            if ident == ajustes.SENTIDO_DA_TELA:
                continue
            nomes = {nome for nome, opcao in OPCAO_DO_SENTIDO.items() if opcao == ident}
            lidos = [n for n, s in sentidos.items() if nome_do_sentido(s["de"]) in nomes]
            if not ajustes.ligado(self.opcoes, ident, padrao):
                saida.append({"opcao": ident, "nivel": 0})
            elif not lidos:
                saida.append({"opcao": ident, "nivel": 0, "frase": LEITURA_NAO_USA, "cego": True})
            elif not nomes & lendo:
                saida.append({"opcao": ident, "nivel": 0, "frase": LEITURA_FORA, "cego": True})
            elif not FONTES_DA_LEITURA.get(ident):
                saida.append({"opcao": ident})
            else:
                saida.append({"opcao": ident, "nivel": self._ouvido_agora(FONTES_DA_LEITURA[ident])})
        return saida

    def _ouvido_agora(self, topicos: tuple[str, ...]) -> int:
        """O mais forte que chegou por ``topicos``, caindo pela metade a cada
        :data:`MEIA_VIDA_DA_LEITURA_S`, de 0 a 100 em passos de :data:`PASSO_DO_MEDIDOR`."""
        agora = self.relogio()
        bruto = max((forca * 0.5 ** (max(0.0, agora - quando) / MEIA_VIDA_DA_LEITURA_S)
                     for t in topicos if t in self.ouvido
                     for forca, quando in [self.ouvido[t]]), default=0.0)
        return round(bruto * 100 / PASSO_DO_MEDIDOR) * PASSO_DO_MEDIDOR

    def ouvir(self, topico: str, dados: dict[str, Any]) -> None:
        """Guarda o quanto o evento trouxe, para o medidor do sentido que lê o tópico."""
        forca = intensidade_do_evento(topico, dados)
        if forca is None:
            return
        agora = self.relogio()
        antes = self._ouvido_agora((topico,)) / 100 if topico in self.ouvido else 0.0
        self.ouvido[topico] = (max(forca, antes), agora)

    def linhas(self) -> list[dict[str, str]]:
        """As linhas da faixa do alto: o estilo, o ajuste que vale, quem sente e quem não recebe
        nada, a tensão da cena em palavras (só no Terror), a memória que espera a chave e a tela."""
        linhas: list[dict[str, str]] = []
        if self.preset is not None and self.receita.universal:
            linhas.append({"rotulo": "Estilo", "valor": self.preset})
        linhas.append({"rotulo": "Ajuste", "valor": self.escolhida.rotulo})
        sentem = self._sentem()
        if sentem:
            linhas.append({"rotulo": "Sentem", "valor": lista_curta([n for n, _u in sentem])})
        fora = [n for n, u in sentem if self._recusa_de_agora(u) is not None]
        if fora and len(fora) < len(sentem):
            linhas.append({"rotulo": "Não recebe", "valor": lista_curta(fora)})
        limiar = self.motor.limiar_do_clima()
        if self.preset == estilos.TERROR and limiar is not None and self.jogo is not None:
            linhas.append({"rotulo": "Tensão da cena",
                           "valor": tensao_da_cena(self.motor.clima(), limiar)})
        if self.jogo is not None and self._le_a_memoria() and not self.memoria_vale:
            linhas.append({"rotulo": "Memória", "valor": ESPERA_A_MEMORIA})
        if self.tela is not None:
            linhas.append({"rotulo": "Tela", "valor": self.tela})
        return linhas[:TETO_DAS_LINHAS]

    def _estado(self) -> dict[str, Any]:
        limiar = self.motor.limiar_do_clima()
        return {"ligado": True, "nivel": self.motor.clima(), "perfil": self.escolhida.rotulo,
                "aparelhos": self.aparelhos(), "conexoes": [],  # (noqa-acento)
                "linhas": self.linhas(), "presentes": self.presentes(),
                "situacao": self.situacao(), "leituras": self.leituras(),
                **({"limiar": limiar} if limiar is not None else {})}

    async def publicar_o_estado(self) -> None:
        """A faixa do alto da janela: a situação, o ajuste que vale e o clima da cena, no nível;
        o que cada sentido lê; e os controles conectados como aparelhos, cada um com a chave
        «Sente os efeitos» na aba Controles."""
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
                 "ligado": ident not in self.calados,
                 "controles": ajustes.controles_do_cartao(self.niveis, ident)}
                for n, (ident, c) in enumerate(self._por_id(), 1)]

    def _calar(self) -> None:
        por_id = self._por_id()
        self.motor.calar({c["uniq"] for ident, c in por_id if ident in self.calados})
        self.motor.nivelar({c["uniq"]: (
            ajustes.nivel(self.niveis, ajustes.CONTROLE_DA_FORCA, ident) / 100,
            ajustes.nivel(self.niveis, ajustes.CONTROLE_DO_VOLUME, ident) / 100)
            for ident, c in por_id})

    def _guardar_os_controles(self) -> None:
        if self.dados is not None:
            with contextlib.suppress(OSError):
                ajustes.guardar_os_controles(self.dados, self.calados, self.niveis)

    async def nivelar(self, controle: str, alvo: Any, valor: Any) -> None:
        """Um nível da Força ou do volume no cartão de um controle: vale no tique seguinte, ao lado
        do outro, sem mexer nele."""
        if not isinstance(alvo, str):
            return
        niveis = ajustes.ajustar_o_nivel(self.niveis, controle, alvo, valor)
        if niveis != self.niveis:
            self.niveis = niveis
            self._guardar_os_controles()
            self._calar()
        await self.publicar_se_mudou()

    async def sentir(self, alvo: Any, valor: Any) -> None:
        """A chave de um controle na aba Jogo: desligada, nenhum efeito chega a ele."""
        if not isinstance(alvo, str) or not isinstance(valor, bool):
            return
        calados = ajustes.sentir(self.calados, alvo, valor)
        if calados != self.calados:
            self.calados = calados
            self._guardar_os_controles()
            self._calar()
        await self.publicar_se_mudou()

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

    def testar(self, acao: str) -> Teste:
        """O botão de testar da aba Efeitos: o efeito toca uma vez em cada controle que sente, e
        o :class:`Teste` guarda o veredito de cada controle conectado."""
        alvos = [c["uniq"] for c in self.controles]
        self.saida.recusados = {k: v for k, v in self.saida.recusados.items()
                                if k[0] not in alvos}
        tocados = self.motor.testar(ajustes.TESTES[acao])
        diario(f"teste: {', '.join(tocados)}" if tocados
               else "teste: a receita de agora não tem este efeito")
        efeitos = self.receita.secao("efeitos")
        canais = {str(efeitos[nome]["canal"]) for nome in tocados}
        teste = Teste(set(tocados), canais, alvos, {
            c["uniq"]: ajustes.nome_do_controle(c, n) for n, c in enumerate(self.controles, 1)})
        desligado = (ajustes.forca(self.motor.opcoes) <= 0
                     or canais <= ajustes.canais_calados(self.motor.opcoes))
        for ident, controle in self._por_id():
            uniq = controle["uniq"]
            if ident in self.calados:
                teste.decidir(uniq, False, MOTIVO_CALADO)
            elif not tocados:
                teste.decidir(uniq, False, MOTIVO_SEM_O_EFEITO)
            elif desligado:
                teste.decidir(uniq, False, MOTIVO_DESLIGADO)
            elif ajustes.nivel(self.niveis, ajustes.CONTROLE_DA_FORCA, ident) <= 0:
                teste.decidir(uniq, False, MOTIVO_SEM_FORCA)
        return teste

    async def responder_o_teste(self, teste: Teste, para: str) -> None:
        """A ``extensao.resposta`` do clique: espera o veredito de cada controle até
        :data:`ESPERA_O_TESTE_S` e devolve ``{controles: [{uniq, tocou, motivo}]}``. O teste já
        está em :attr:`testes` desde o clique: o tique seguinte é o que escreve."""
        try:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(teste.pronto.wait(), ESPERA_O_TESTE_S)
        finally:
            self.testes.remove(teste)
        controles = teste.fechar()
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.porta.pedir("extensao.resposta", {"para": para,
                                                         "dados": {"controles": controles}})

    async def ver_a_tela(self) -> None:
        """O clique «Ver a tela»: ``tela.ver`` e, aceito, a assinatura do ``jogo.tela``. O
        segundo clique para. O Hefesto que não conhece o pedido vira a linha «Tela», uma vez por
        clique, e nada se assina."""
        if self.vendo:
            await self.parar_de_ver()
            return
        try:
            await self.porta.pedir("tela.ver", {})
        except RecusaDaPorta as exc:
            antes = self.tela
            self.tela = TELA_SEM_O_PEDIDO if exc.codigo == METODO_DESCONHECIDO else TELA_RECUSADA
            if self.tela != antes:
                diario(f"tela.ver recusado: {exc}")
            await self.publicar_se_mudou()
            return
        except (RuntimeError, ConnectionError, asyncio.TimeoutError) as exc:
            diario(f"tela.ver sem resposta: {exc}")
            return
        await self._a_tela(True)

    async def parar_de_ver(self) -> None:
        """«Parar de ver», o segundo clique ou o jogo que fecha: ``tela.parar`` e a desassinatura."""
        if not self.vendo:
            if self.tela is not None:
                self.tela = None
                await self.publicar_se_mudou()
            return
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.porta.pedir("tela.parar", {})
        await self._a_tela(False)

    async def _a_tela(self, vendo: bool) -> None:
        self.vendo = vendo
        self.tela = TELA_VENDO if vendo else None
        self.opcoes = ajustes.com_a_tela(self.opcoes, vendo)
        self.motor.ajustar(self.opcoes)
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.assinar()
        await self.publicar_se_mudou()

    def aplicar_o_estilo(self) -> None:
        """O preset do universal: o escolhido na janela, ou o do estilo que o Hefesto diz. Sem
        escolha à mão e sem o estilo dito (o Hefesto que não o publica), o padrão da receita."""
        escolha = self.opcoes.get(estilos.OPCAO, estilos.PELO_JOGO)
        if escolha not in estilos.PRESETS and not self.estilo_dito:
            self.preset = None
            self.motor.estilo()
            return
        self.preset = estilos.preset(escolha, self.estilo_do_jogo)
        self.motor.estilo(*estilos.do_preset(self.preset))

    async def reler_as_opcoes(self) -> None:
        """O ``opcoes.json`` mudou: as entradas valem já, e a opção da receita pode trocá-la."""
        antes = self.escolha
        self.opcoes = ajustes.com_a_tela(ler_as_opcoes(self.dados), self.vendo)
        self.motor.ajustar(self.opcoes)
        self.aplicar_o_estilo()
        if self.escolha != antes:
            await self.escolher()
        with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
            await self.assinar()
        await self.publicar_se_mudou()

    async def atualizar_os_controles(self) -> None:
        resposta = await self.porta.pedir("controles.lista", {})
        lista = resposta.get("controles", [])
        self.controles = [c for c in (lista if isinstance(lista, list) else [])
                          if isinstance(c, dict) and isinstance(c.get("uniq"), str)]
        self.motor.controles(self.controles)
        self._calar()
        await self.publicar_se_mudou()

    async def rever_os_controles(self, sempre: bool = False) -> None:
        """A lista de novo quando um controle está sem a cor do plástico, ou ``sempre``."""
        if sempre or not all(isinstance(c.get("cor"), str) and c["cor"].strip()
                             for c in self.controles):
            with contextlib.suppress(RuntimeError, ConnectionError, asyncio.TimeoutError):
                await self.atualizar_os_controles()

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
            antes, self.jogo = self.jogo, jogo if isinstance(jogo, str) and jogo else None
            em_cena, perfil = dados.get("em_cena"), dados.get("perfil")
            self.em_cena = em_cena if isinstance(em_cena, bool) else self.jogo is not None
            self.nome_do_jogo = (perfil.strip() if self.em_cena and isinstance(perfil, str)
                                 and perfil.strip() else None)
            if self.vendo and antes is not None and self.jogo != antes:
                await self.parar_de_ver()
            self.memoria_vale = dados.get("memoria") is True
            await self.escolher()
            await self.publicar_se_mudou()
            if self.jogo is not None:
                self.procurar_em_fundo()
        elif topico == "jogo.estilo" and isinstance(dados, dict):
            estilo = dados.get("estilo")
            self.estilo_do_jogo = estilo if isinstance(estilo, str) and estilo else None
            self.estilo_dito = True
            self.aplicar_o_estilo()
            await self.publicar_se_mudou()
        elif topico == "extensao.opcao" and isinstance(dados, dict):
            ident, valor = dados.get("id"), dados.get("valor")
            if (isinstance(ident, str) and ident != ajustes.SENTIDO_DA_TELA
                    and isinstance(valor, (bool, int, float, str))):
                self.motor.opcoes[ident] = valor
                if ident == estilos.OPCAO:
                    self.opcoes = {**self.opcoes, ident: valor}
                    self.aplicar_o_estilo()
                    await self.publicar_se_mudou()
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") == ajustes.ACAO_DE_LIGAR):  # (noqa-acento)
            await self.sentir(dados.get("alvo"), dados.get("valor"))
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") in (ajustes.CONTROLE_DA_FORCA,  # (noqa-acento)
                                        ajustes.CONTROLE_DO_VOLUME)):
            await self.nivelar(str(dados.get("acao")), dados.get("alvo"), dados.get("valor"))  # (noqa-acento)
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") in ajustes.TESTES):  # (noqa-acento)
            teste = self.testar(str(dados.get("acao")))  # (noqa-acento)
            if isinstance(para := dados.get("id"), str) and para:
                self.testes.append(teste)
                tarefa = asyncio.create_task(self.responder_o_teste(teste, para))
                self.respondendo.add(tarefa)
                tarefa.add_done_callback(self.respondendo.discard)
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") == ajustes.ACAO_DE_VER_A_TELA):  # (noqa-acento)
            await self.ver_a_tela()
        elif (topico == "extensao.acao" and isinstance(dados, dict)
              and dados.get("acao") == ajustes.ACAO_DE_PARAR_DE_VER):  # (noqa-acento)
            await self.parar_de_ver()
        if topico == "jogo.memoria" and not self.memoria_vale:
            return True
        if isinstance(topico, str) and isinstance(dados, dict):
            self.ouvir(topico, dados)
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
    if dados is not None:
        with contextlib.suppress(OSError):
            ajustes.migrar(dados)
    porta = await Porta.abrir(caminho)
    await porta.pedir("mod.ola", {"ficha": ficha})
    biblioteca = Biblioteca(PASTA_DAS_ESTUDADAS, dados, carregar_o_universal, diario)
    opcoes = ler_as_opcoes(dados)
    extensao = Extensao(porta, biblioteca.para(None, escolha_da_receita(opcoes)), biblioteca,
                        dados, Comunidade(dados) if dados is not None else None)
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

    async def resumir_o_minuto() -> None:
        while True:
            await asyncio.sleep(RESUMO_A_CADA_S)
            await extensao.rever_os_controles(sempre=True)
            extensao.fechar_o_minuto()

    async def esperar_a_cor() -> None:
        while True:
            await asyncio.sleep(RELE_OS_CONTROLES_S)
            await extensao.rever_os_controles()

    async def acompanhar_o_clima() -> None:
        while True:
            await asyncio.sleep(PUBLICA_O_CLIMA_S)
            await extensao.publicar_se_mudou()

    ouvir = asyncio.create_task(ouvir_a_porta())
    vigiar = asyncio.create_task(vigiar_as_opcoes())
    clima = asyncio.create_task(acompanhar_o_clima())
    resumo = asyncio.create_task(resumir_o_minuto())
    cor = asyncio.create_task(esperar_a_cor())
    motor = asyncio.create_task(rodar_o_laco(extensao.motor, extensao.saida, fim,
                                             pode_repousar=lambda: not extensao.testes))
    try:
        await fim.wait()
        with contextlib.suppress(ConnectionError, asyncio.TimeoutError, RuntimeError):
            await asyncio.wait_for(motor, 2.0)
        extensao.fechar_o_minuto()
        if extensao.vendo:
            with contextlib.suppress(ConnectionError, asyncio.TimeoutError, RuntimeError):
                await asyncio.wait_for(extensao.porta.pedir("tela.parar", {}),
                                       ESPERA_O_FIM_DA_TELA_S)
    finally:
        tarefas = [ouvir, vigiar, clima, resumo, cor, motor, *extensao.respondendo,
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
