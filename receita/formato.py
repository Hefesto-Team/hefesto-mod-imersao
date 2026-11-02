"""O formato 1 da receita: JSON versionado, validação estrita e o erro com a linha.

A receita diz ao motor o que ler do jogo (``sentidos``), o que calcular (``derivados``), quando a
cena muda (``estados``), o que tocar no controle (``efeitos``) e a ligação entre os dois
(``regras``). Campo desconhecido recusa, em todo nível; o arquivo passa de 64 KB e recusa antes
de ser lido; expressão fora da lista fechada recusa; o ciclo entre derivados e estados recusa; e
o gatilho fala os sete modos com as faixas que o console aceita. Um sentido lê um tópico da porta
ou um sentido universal (``sentido.<nome>``), e este pede as permissões de todas as origens dele.
"""
from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, field
from typing import Any

import sentidos as universais
from efeitos import luzes
from receita import expressao
from receita.json_com_linhas import Caminho, JsonRecusado, ler, linha_de

FORMATO = 1
MOTOR = 1
TAMANHO_MAXIMO = 64 * 1024

ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
CHAVE_DE_JOGO = re.compile(r"^steam_app_[0-9]{1,12}$")
BUILD = re.compile(r"^[0-9]{1,12}$")
CAMPO_DO_EVENTO = re.compile(r"^[a-z_][a-z0-9_]*(?:\.[a-z0-9_]+){0,3}$")
NOME_DO_EVENTO = re.compile(r"^[a-z][a-z0-9_.]{0,39}$")
COR = re.compile(r"^#[0-9a-fA-F]{6}$")
COR_DA_ENTRADA = re.compile(r"^\$[a-z][a-z0-9_]*$")
HEXA = re.compile(r"^0x[0-9a-fA-F]{1,16}$")
BASE64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
TETO_DA_IMPRESSAO = 4096
ANCORAS = ("canto_sup_esq", "canto_sup_dir", "canto_inf_esq", "canto_inf_dir")
_CLAUSULA = re.compile(r"^(>=|<=|==|>|<)?\s*(\d+)$")

TOPICOS_POR_CONTROLE = (
    "conexao", "entradas", "botoes", "movimento", "bateria",  # (noqa-acento)
    "jogo.vibracao", "jogo.gatilho", "jogo.haptica", "microfone.nivel",
)
TOPICOS_GLOBAIS = ("perfil.jogo", "jogo.som", "jogo.tela", "jogo.memoria", "jogo.identidade")
TOPICOS = TOPICOS_POR_CONTROLE + TOPICOS_GLOBAIS
PERMISSOES = tuple(f"ler:{t}" for t in TOPICOS)
TOPICOS_DOS_SENTIDOS = universais.TOPICOS
CANAIS = ("haptica", "motor", "gatilho", "luz", "som", "leds")
PADROES_PCM = ("coracao", "susto", "estalo")  # (noqa-acento)
SONS = ("susto", "estalo", "recorte")
LADOS = ("esquerdo", "direito", "ambos")
LADOS_DO_GATILHO = ("l2", "r2", "ambos")
JOGADORES = ("p1", "p2", "p3", "p4")
MODOS_DO_GATILHO = (
    "desliga", "resistencia", "arma", "vibracao", "resistencia_por_zona", "rampa",  # (noqa-acento)
    "vibracao_por_zona",
)
ZONAS = 10


class ReceitaRecusada(ValueError):
    """A receita fora do formato: cada erro com a linha em que aparece, na ordem das linhas."""

    def __init__(self, erros: list[tuple[int, str]]) -> None:
        self.erros = sorted(erros)
        super().__init__("\n".join(f"linha {linha}: {frase}" for linha, frase in self.erros))

    @property
    def linha(self) -> int:
        return self.erros[0][0]


Erros = list[tuple[Caminho, str]]


def _onde(caminho: Caminho) -> str:
    return ".".join(str(p) for p in caminho) or "a receita"


def _numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


class Esquema:
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class Texto(Esquema):
    maximo: int = 120
    forma: re.Pattern[str] | None = None
    escolhas: tuple[str, ...] = ()

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, str):
            erros.append((caminho, "pede um texto"))
        elif self.escolhas and valor not in self.escolhas:
            erros.append((caminho, f"«{valor}» fora da lista ({', '.join(self.escolhas)})"))
        elif not 1 <= len(valor) <= self.maximo:
            erros.append((caminho, f"pede de 1 a {self.maximo} letras"))
        elif self.forma is not None and not self.forma.match(valor):
            erros.append((caminho, f"«{valor}» fora da forma"))


@dataclass(frozen=True)
class Inteiro(Esquema):
    minimo: int
    maximo: int

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, int) or isinstance(valor, bool):
            erros.append((caminho, "pede um número inteiro"))
        elif not self.minimo <= valor <= self.maximo:
            erros.append((caminho, f"{valor} fora da faixa de {self.minimo} a {self.maximo}"))


@dataclass(frozen=True)
class Real(Esquema):
    minimo: float
    maximo: float

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not _numero(valor):
            erros.append((caminho, "pede um número"))
        elif not self.minimo <= valor <= self.maximo:
            erros.append((caminho, f"{valor} fora da faixa de {self.minimo:g} a {self.maximo:g}"))


@dataclass(frozen=True)
class RealOuExpressao(Esquema):
    minimo: float
    maximo: float

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if isinstance(valor, str):
            Texto(expressao.TAMANHO_MAXIMO).conferir(valor, caminho, erros)
        else:
            Real(self.minimo, self.maximo).conferir(valor, caminho, erros)


@dataclass(frozen=True)
class InteiroOuExpressao(Esquema):
    minimo: int
    maximo: int

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if isinstance(valor, str):
            Texto(expressao.TAMANHO_MAXIMO).conferir(valor, caminho, erros)
        else:
            Inteiro(self.minimo, self.maximo).conferir(valor, caminho, erros)


@dataclass(frozen=True)
class PadraoDaEntrada(Esquema):
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not _numero(valor) and not isinstance(valor, bool) and not (
                isinstance(valor, str) and COR.match(valor)):
            erros.append((caminho, "pede um número, verdadeiro/falso ou uma cor #rrggbb"))


@dataclass(frozen=True)
class CorOuEntrada(Esquema):
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, str) or not (COR.match(valor) or COR_DA_ENTRADA.match(valor)):
            erros.append((caminho, "pede uma cor #rrggbb ou a entrada de cor ($nome)"))


@dataclass(frozen=True)
class Lista(Esquema):
    item: Esquema
    maximo: int
    minimo: int = 0
    unicos: bool = False

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, list):
            erros.append((caminho, "pede uma lista"))
            return
        if not self.minimo <= len(valor) <= self.maximo:
            faixa = (f"exatamente {self.minimo}" if self.minimo == self.maximo
                     else f"de {self.minimo} a {self.maximo}")
            erros.append((caminho, f"pede {faixa} itens, e tem {len(valor)}"))
        for i, item in enumerate(valor):
            self.item.conferir(item, (*caminho, i), erros)
        if self.unicos:
            vistos: set[Any] = set()
            for i, item in enumerate(valor):
                if isinstance(item, str) and item in vistos:
                    erros.append(((*caminho, i), f"«{item}» repetido"))
                vistos.add(item)


@dataclass(frozen=True)
class TextoOuLista(Esquema):
    item: Texto
    maximo: int

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if isinstance(valor, list):
            Lista(self.item, self.maximo, minimo=1, unicos=True).conferir(valor, caminho, erros)
        else:
            self.item.conferir(valor, caminho, erros)


@dataclass(frozen=True)
class Dicionario(Esquema):
    valor: Esquema
    maximo: int

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, dict):
            erros.append((caminho, "pede um objeto de id → valor"))
            return
        if len(valor) > self.maximo:
            erros.append((caminho, f"pede até {self.maximo} itens, e tem {len(valor)}"))
        for chave, item in valor.items():
            if not ID.match(chave):
                erros.append(((*caminho, chave), f"o id «{chave}» fora da forma (a-z, 0-9, _)"))
            elif chave in expressao.PALAVRAS or chave in expressao.FUNCOES:
                erros.append(((*caminho, chave), f"o id «{chave}» é palavra das expressões"))
            self.valor.conferir(item, (*caminho, chave), erros)


@dataclass(frozen=True)
class Objeto(Esquema):
    campos: dict[str, Esquema]
    obrigatorios: frozenset[str] = frozenset()
    extra: str = "ignore"

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, dict):
            erros.append((caminho, "pede um objeto"))
            return
        for nome in sorted(self.obrigatorios - valor.keys()):
            erros.append((caminho, f"falta o campo «{nome}»"))
        for nome, item in valor.items():
            esquema = self.campos.get(nome)
            if esquema is not None:
                esquema.conferir(item, (*caminho, nome), erros)
            elif self.extra == "forbid":
                erros.append(((*caminho, nome), f"campo desconhecido «{nome}»"))


def estrito(obrigatorios: tuple[str, ...] = (), **campos: Esquema) -> Objeto:
    """O objeto da receita: o campo que o formato não conhece recusa."""
    return Objeto(campos, frozenset(obrigatorios), extra="forbid")


@dataclass(frozen=True)
class Discriminado(Esquema):
    campo: str
    variantes: dict[str, Esquema]

    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, dict):
            erros.append((caminho, "pede um objeto"))
            return
        chave = valor.get(self.campo)
        if chave not in self.variantes:
            onde = (*caminho, self.campo) if self.campo in valor else caminho
            erros.append((onde, f"«{self.campo}» pede um de: {', '.join(self.variantes)}"))
            return
        self.variantes[chave].conferir(valor, caminho, erros)


@dataclass(frozen=True)
class Formato(Esquema):
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if isinstance(valor, int) and not isinstance(valor, bool) and valor > FORMATO:
            erros.append((caminho, f"o formato {valor} é mais novo que o deste motor ({FORMATO})"))
        else:
            Inteiro(FORMATO, FORMATO).conferir(valor, caminho, erros)


def clausulas(faixa: str) -> list[tuple[str, int]]:
    """As cláusulas de uma faixa como ``">=1,<2"``, a mesma sintaxe do manifesto."""
    saida = []
    for parte in faixa.split(","):
        achado = _CLAUSULA.match(parte.strip())
        if achado is None:
            raise ValueError(f"cláusula ilegível: «{parte.strip()}»")
        saida.append((achado.group(1) or "==", int(achado.group(2))))
    return saida


def aceita(faixa: str, versao: int) -> bool:
    testes = {">=": versao.__ge__, "<=": versao.__le__, "==": versao.__eq__,
              ">": versao.__gt__, "<": versao.__lt__}
    return all(testes[op](n) for op, n in clausulas(faixa))


@dataclass(frozen=True)
class FaixaDoMotor(Esquema):
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if not isinstance(valor, str) or len(valor) > 40:
            erros.append((caminho, "pede uma faixa como «>=1,<2»"))
            return
        try:
            serve = aceita(valor, MOTOR)
        except ValueError as exc:
            erros.append((caminho, str(exc)))
            return
        if not serve:
            erros.append((caminho, f"a faixa «{valor}» não aceita o motor {MOTOR}"))


_LEITURA = estrito(
    ("tipo", "modulo", "base"),  # (noqa-acento)
    tipo=Texto(escolhas=("u8", "i8", "u16", "i16", "u32", "i32", "f32", "f64")),
    modulo=Texto(120),
    base=Texto(18, HEXA),
    saltos=Lista(Texto(18, HEXA), 8),
)

_IMPRESSAO = estrito(
    ("bandas", "quadros", "vetor"),
    bandas=Inteiro(1, 64),
    quadros=Inteiro(1, 64),
    vetor=Texto(5464, BASE64),
    limiar=Real(0.5, 1.0),
)

_REGIAO = estrito(
    ("x", "y", "w", "h"),
    ancora=Texto(escolhas=ANCORAS),
    x=Real(0.0, 1.0),
    y=Real(0.0, 1.0),
    w=Real(0.0, 1.0),
    h=Real(0.0, 1.0),
    referencia=Lista(Inteiro(1, 16384), 2, minimo=2),
)

_SENTIDO = estrito(
    ("de", "especie"),
    de=Texto(escolhas=TOPICOS + TOPICOS_DOS_SENTIDOS),
    especie=Texto(escolhas=("nivel", "estado", "evento")),
    nome=Texto(40, NOME_DO_EVENTO),
    campo=Texto(80, CAMPO_DO_EVENTO),
    igual=Texto(40),
    escala=Lista(Real(-1e9, 1e9), 2, minimo=2),
    limiar=Real(-1e9, 1e9),
    leitura=_LEITURA,
    impressao=_IMPRESSAO,
    regiao=_REGIAO,
)

_ACUMULA = estrito(
    ("sobe_com", "passo", "meia_vida_ms"),
    sobe_com=Lista(Texto(32, ID), 8, minimo=1, unicos=True),
    passo=Real(0.0, 1.0),
    meia_vida_ms=Inteiro(1, 600_000),
)

_DERIVADO = estrito(expr=Texto(expressao.TAMANHO_MAXIMO), acumula=_ACUMULA)

_ESTADO = estrito(
    ("quando",),
    quando=Texto(expressao.TAMANHO_MAXIMO),
    histerese=Real(0.0, 1e9),
    minimo_ms=Inteiro(0, 600_000),
)

_ENTRADA = estrito(
    ("rotulo", "tipo", "padrao"),  # (noqa-acento)
    rotulo=Texto(40),
    tipo=Texto(escolhas=("deslizante", "ligado", "cor")),
    minimo=Real(-1e9, 1e9),
    maximo=Real(-1e9, 1e9),
    padrao=PadraoDaEntrada(),
)

_DURA = Inteiro(1, 600_000)
_POSICAO = Inteiro(0, 9)
_FORCA_DO_GATILHO = Inteiro(1, 8)
_ZONA = Inteiro(0, 8)
_FREQUENCIA = Inteiro(0, 255)


def _gatilho(obrigatorios: tuple[str, ...] = (), **params: Esquema) -> Objeto:
    return estrito(("canal", "modo", "lado", *obrigatorios), canal=Texto(escolhas=CANAIS),
                   modo=Texto(escolhas=MODOS_DO_GATILHO), lado=Texto(escolhas=LADOS_DO_GATILHO),
                   dura_ms=_DURA, **params)


_EFEITO_DE_GATILHO = Discriminado("modo", {
    "desliga": _gatilho(),
    "resistencia": _gatilho(("posicao", "forca"), posicao=_POSICAO, forca=_FORCA_DO_GATILHO),  # (noqa-acento)
    "arma": _gatilho(("inicio", "fim", "forca"), inicio=Inteiro(2, 7), fim=Inteiro(3, 8),
                     forca=_FORCA_DO_GATILHO),
    "vibracao": _gatilho(("posicao", "amplitude", "frequencia"), posicao=_POSICAO,  # (noqa-acento)
                         amplitude=_FORCA_DO_GATILHO, frequencia=_FREQUENCIA),
    "resistencia_por_zona": _gatilho(("forcas",), forcas=Lista(_ZONA, ZONAS, minimo=ZONAS)),
    "rampa": _gatilho(("inicio", "fim", "forca_inicio", "forca_fim"), inicio=Inteiro(0, 8),
                      fim=Inteiro(1, 9), forca_inicio=_FORCA_DO_GATILHO,
                      forca_fim=_FORCA_DO_GATILHO),
    "vibracao_por_zona": _gatilho(("frequencia", "amplitudes"), frequencia=_FREQUENCIA,  # (noqa-acento)
                                  amplitudes=Lista(_ZONA, ZONAS, minimo=ZONAS)),
})


@dataclass(frozen=True)
class EfeitoDeGatilho(Esquema):
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        antes = len(erros)
        _EFEITO_DE_GATILHO.conferir(valor, caminho, erros)
        if len(erros) != antes:
            return
        modo = valor["modo"]
        if modo in ("arma", "rampa") and valor["fim"] <= valor["inicio"]:
            erros.append(((*caminho, "fim"), (f"o fim ({valor['fim']}) tem de passar do início "
                                             f"({valor['inicio']})")))
        if valor.get("frequencia") == 0:  # (noqa-acento)
            erros.append(((*caminho, "frequencia"),  # (noqa-acento)
                          "a frequência 0 desliga o gatilho: use o modo «desliga»"))
        zonas = {"resistencia_por_zona": "forcas", "vibracao_por_zona": "amplitudes"}.get(modo)
        if zonas and not any(valor[zonas]):
            erros.append(((*caminho, zonas), "todas as zonas sem força: use o modo «desliga»"))


_EFEITO = Discriminado("canal", {
    "haptica": estrito(("canal", "padrao"), canal=Texto(escolhas=CANAIS),  # (noqa-acento)
                       padrao=Texto(escolhas=PADROES_PCM), forca=RealOuExpressao(0.0, 1.0),
                       bpm=RealOuExpressao(30.0, 220.0), lado=Texto(escolhas=LADOS),
                       dura_ms=_DURA),
    "motor": estrito(("canal", "forca"), canal=Texto(escolhas=CANAIS),
                     forca=RealOuExpressao(0.0, 1.0), lado=Texto(escolhas=LADOS), dura_ms=_DURA),
    "gatilho": EfeitoDeGatilho(),
    "luz": estrito(("canal", "cor"), canal=Texto(escolhas=CANAIS), cor=CorOuEntrada(),
                   brilho=Real(0.0, 1.0), dura_ms=_DURA),
    "som": estrito(("canal", "som"), canal=Texto(escolhas=CANAIS), som=Texto(escolhas=SONS),
                   volume=Real(0.0, 1.0)),
    "leds": estrito(("canal", "lado"), canal=Texto(escolhas=CANAIS), lado=Texto(escolhas=LADOS),
                    dura_ms=Inteiro(1, luzes.PRAZO_MAXIMO_MS)),
})

_EFEITO_ID = Texto(32, ID)

_PARA = Texto(escolhas=("todos", "quem_levou"))


@dataclass(frozen=True)
class Para(Esquema):
    def conferir(self, valor: Any, caminho: Caminho, erros: Erros) -> None:
        if isinstance(valor, list):
            Lista(Texto(escolhas=JOGADORES), 4, minimo=1, unicos=True).conferir(
                valor, caminho, erros)
        else:
            _PARA.conferir(valor, caminho, erros)

_REGRA = estrito(
    ("quando", "entao"),
    quando=Texto(expressao.TAMANHO_MAXIMO),
    entao=TextoOuLista(_EFEITO_ID, 8),
    senao=TextoOuLista(_EFEITO_ID, 8),
    prioridade=Inteiro(0, 100),
    espera_ms=InteiroOuExpressao(0, 600_000),
    para=Para(),
)

_CONFERE = estrito(
    ("sentido",),
    sentido=Texto(32, ID),
    faixa=Lista(Real(-1e9, 1e9), 2, minimo=2),
    concorda_com=Texto(32, ID),
    tolerancia=Real(0.0, 1e9),
)

RECEITA = estrito(
    ("formato", "motor"),
    formato=Formato(),
    motor=FaixaDoMotor(),
    jogo=estrito(
        chave=Texto(40, CHAVE_DE_JOGO),
        janela=Lista(Texto(120), 8, minimo=1, unicos=True),
        builds=estrito(("steam_buildid",), steam_buildid=Lista(Texto(12, BUILD), 2, minimo=2)),
        leitura_de_memoria=Texto(escolhas=("nao", "pede", "nunca")),  # (noqa-acento)
    ),
    permissoes=Lista(Texto(escolhas=PERMISSOES), len(PERMISSOES), unicos=True),
    entradas=Dicionario(_ENTRADA, 16),
    sentidos=Dicionario(_SENTIDO, 64),
    derivados=Dicionario(_DERIVADO, 32),
    estados=Dicionario(_ESTADO, 32),
    efeitos=Dicionario(_EFEITO, 64),
    regras=Lista(_REGRA, 32),
    confere=Lista(_CONFERE, 32),
)


@dataclass(frozen=True)
class Receita:
    """A receita validada: os dados, as expressões já analisadas e a ordem de cálculo."""

    dados: dict[str, Any]
    expressoes: dict[Caminho, expressao.No] = field(default_factory=dict)
    ordem: tuple[str, ...] = ()
    universal: bool = False

    def secao(self, nome: str) -> dict[str, Any]:
        valor = self.dados.get(nome, {})
        return valor if isinstance(valor, dict) else {}

    @property
    def regras(self) -> list[dict[str, Any]]:
        return list(self.dados.get("regras", []))

    @property
    def vazia(self) -> bool:
        return not self.secao("sentidos") and not self.regras


def receita_vazia() -> Receita:
    """A receita sem sentido nem regra: não toca nada."""
    return Receita({"formato": FORMATO, "motor": f">={MOTOR},<{MOTOR + 1}"})


def _expressao(texto: str, caminho: Caminho, erros: Erros,
               analisadas: dict[Caminho, expressao.No]) -> expressao.No | None:
    try:
        no = expressao.analisar(texto)
    except expressao.ExpressaoRecusada as exc:
        erros.append((caminho, f"expressão recusada na {exc}"))
        return None
    analisadas[caminho] = no
    return no


def _ciclo(grafo: dict[str, set[str]]) -> list[str] | None:
    cor: dict[str, int] = {}
    pilha: list[str] = []

    def visitar(no: str) -> list[str] | None:
        cor[no] = 1
        pilha.append(no)
        for vizinho in sorted(grafo.get(no, ())):
            if cor.get(vizinho) == 1:
                return [*pilha[pilha.index(vizinho):], vizinho]
            if vizinho not in cor and (achado := visitar(vizinho)):
                return achado
        cor[no] = 2
        pilha.pop()
        return None

    for no in sorted(grafo):
        if no not in cor and (achado := visitar(no)):
            return achado
    return None


def _ordem(grafo: dict[str, set[str]]) -> tuple[str, ...]:
    feitos: list[str] = []

    def visitar(no: str) -> None:
        if no in feitos:
            return
        for vizinho in sorted(grafo.get(no, ())):
            visitar(vizinho)
        feitos.append(no)

    for no in sorted(grafo):
        visitar(no)
    return tuple(feitos)


def _conferir_a_impressao(sentido: dict[str, Any], caminho: Caminho, erros: Erros) -> None:
    impressao = sentido.get("impressao")  # (noqa-acento)
    if impressao is None:
        return
    if sentido["de"] != "jogo.som" or sentido["especie"] != "evento":
        erros.append(((*caminho, "impressao"),  # (noqa-acento)
                      "só o evento de jogo.som tem «impressao»"))  # (noqa-acento)
        return
    try:
        vetor = base64.b64decode(impressao["vetor"], validate=True)
    except (binascii.Error, ValueError):
        erros.append(((*caminho, "impressao", "vetor"), "o vetor não é base64"))  # (noqa-acento)
        return
    if len(vetor) > TETO_DA_IMPRESSAO:
        erros.append(((*caminho, "impressao", "vetor"),  # (noqa-acento)
                      f"a impressão tem {len(vetor)} bytes, e o teto é {TETO_DA_IMPRESSAO}"))
    elif len(vetor) != impressao["bandas"] * impressao["quadros"]:
        erros.append(((*caminho, "impressao", "vetor"),  # (noqa-acento)
                      "o vetor não tem bandas × quadros números"))


def _conferir_a_regiao(sentido: dict[str, Any], caminho: Caminho, erros: Erros) -> None:
    regiao = sentido.get("regiao")
    if regiao is None:
        return
    if sentido["de"] != "jogo.tela" or sentido["especie"] != "nivel":
        erros.append(((*caminho, "regiao"), "só o nível de jogo.tela tem «regiao»"))
    elif regiao["w"] <= 0 or regiao["h"] <= 0:
        erros.append(((*caminho, "regiao"), "a região pede largura e altura"))
    elif regiao["x"] + regiao["w"] > 1 or regiao["y"] + regiao["h"] > 1:
        erros.append(((*caminho, "regiao"), "a região passa da borda da tela"))


def _semantica(dados: dict[str, Any], erros: Erros) -> Receita:
    analisadas: dict[Caminho, expressao.No] = {}
    sentidos: dict[str, Any] = dados.get("sentidos", {})
    derivados: dict[str, Any] = dados.get("derivados", {})
    estados: dict[str, Any] = dados.get("estados", {})
    entradas: dict[str, Any] = dados.get("entradas", {})
    efeitos: dict[str, Any] = dados.get("efeitos", {})
    permissoes = set(dados.get("permissoes", []))  # (noqa-acento)
    memoria = dados.get("jogo", {}).get("leitura_de_memoria", "nao")  # (noqa-acento)

    donos: dict[str, str] = {}
    for secao, grupo in (("sentidos", sentidos), ("derivados", derivados), ("estados", estados)):
        for ident in grupo:
            if ident in donos:
                erros.append(((secao, ident), f"o id «{ident}» já é de {donos[ident]}"))
            donos.setdefault(ident, secao)

    builds = dados.get("jogo", {}).get("builds", {}).get("steam_buildid")
    if builds and int(builds[0]) > int(builds[1]):
        erros.append((("jogo", "builds", "steam_buildid"), "a build de partida passa da de fim"))

    for ident, entrada in entradas.items():
        caminho: Caminho = ("entradas", ident)
        if entrada["tipo"] == "cor":
            if not isinstance(entrada["padrao"], str) or not COR.match(entrada["padrao"]):  # (noqa-acento)
                erros.append(((*caminho, "padrao"), "a entrada de cor tem padrão #rrggbb"))  # (noqa-acento)
            for campo in ("minimo", "maximo"):  # (noqa-acento)
                if campo in entrada:
                    erros.append(((*caminho, campo), "a entrada de cor não tem faixa"))
            continue
        if entrada["tipo"] == "ligado":
            if not isinstance(entrada["padrao"], bool):  # (noqa-acento)
                erros.append(((*caminho, "padrao"), "a entrada ligado tem padrão verdadeiro/falso"))  # (noqa-acento)
            for campo in ("minimo", "maximo"):  # (noqa-acento)
                if campo in entrada:
                    erros.append(((*caminho, campo), "a entrada ligado não tem faixa"))
            continue
        if "minimo" not in entrada or "maximo" not in entrada:  # (noqa-acento)
            erros.append((caminho, "o deslizante pede «minimo» e «maximo»"))  # (noqa-acento)
            continue
        if entrada["minimo"] >= entrada["maximo"]:  # (noqa-acento)
            erros.append(((*caminho, "maximo"), "o máximo tem de passar do mínimo"))  # (noqa-acento)
        padrao = entrada["padrao"]  # (noqa-acento)
        if not _numero(padrao) or not entrada["minimo"] <= padrao <= entrada["maximo"]:  # (noqa-acento)
            erros.append(((*caminho, "padrao"), "o padrão fica fora da faixa do deslizante"))  # (noqa-acento)

    for ident, sentido in sentidos.items():
        caminho = ("sentidos", ident)
        for origem in sorted(universais.origens([sentido["de"]])):
            if f"ler:{origem}" not in permissoes:
                erros.append(((*caminho, "de"), (f"lê «{sentido['de']}» sem declarar "
                                                f"«ler:{origem}» nas permissoes")))  # (noqa-acento)
        if sentido["de"] == "jogo.memoria":
            if memoria != "pede":
                erros.append(((*caminho, "de"), (f"lê a memória com a leitura_de_memoria "
                                                f"«{memoria}»: só «pede» lê")))
            if "leitura" not in sentido:
                erros.append((caminho, "o sentido da memória pede a «leitura»"))
        elif "leitura" in sentido:
            erros.append(((*caminho, "leitura"), "só o sentido de jogo.memoria tem «leitura»"))
        _conferir_a_impressao(sentido, caminho, erros)
        _conferir_a_regiao(sentido, caminho, erros)
        if (sentido["especie"] != "evento" and "campo" not in sentido
                and "leitura" not in sentido and "regiao" not in sentido):
            erros.append((caminho, "o sentido de nível ou de estado pede o «campo»"))
        escala = sentido.get("escala")
        if escala and escala[0] == escala[1]:
            erros.append(((*caminho, "escala"), "a escala pede duas pontas diferentes"))
        if "igual" in sentido and "campo" not in sentido:
            erros.append(((*caminho, "igual"), "«igual» compara o «campo», que falta"))

    def conferir_nomes(no: expressao.No, caminho: Caminho) -> None:
        for nome in sorted(expressao.nomes(no)):
            if nome not in donos:
                erros.append((caminho, (f"a expressão lê «{nome}», que não é sentido, derivado "
                                       "nem estado")))
        for nome in sorted(expressao.entradas(no)):
            if nome not in entradas:
                erros.append((caminho, f"a expressão lê a entrada «${nome}», que não existe"))
            elif entradas[nome]["tipo"] == "cor":
                erros.append((caminho, f"a entrada «${nome}» é uma cor e não entra em conta"))

    grafo: dict[str, set[str]] = {}
    caminho_do_no: dict[str, Caminho] = {}
    for ident, derivado in derivados.items():
        caminho = ("derivados", ident)
        if ("expr" in derivado) == ("acumula" in derivado):
            erros.append((caminho, "o derivado pede um, e só um, de «expr» e «acumula»"))
            continue
        if "expr" in derivado:
            no = _expressao(derivado["expr"], (*caminho, "expr"), erros, analisadas)
            caminho_do_no[ident] = (*caminho, "expr")
            if no is not None:
                conferir_nomes(no, (*caminho, "expr"))
                grafo[ident] = expressao.nomes(no) & (derivados.keys() | estados.keys())
            continue
        grafo[ident] = set()
        for i, evento in enumerate(derivado["acumula"]["sobe_com"]):
            if sentidos.get(evento, {}).get("especie") != "evento":
                erros.append(((*caminho, "acumula", "sobe_com", i),
                              f"«{evento}» não é sentido de evento"))
    for ident, estado in estados.items():
        caminho = ("estados", ident, "quando")
        caminho_do_no[ident] = caminho
        no = _expressao(estado["quando"], caminho, erros, analisadas)
        if no is None:
            continue
        conferir_nomes(no, caminho)
        grafo[ident] = expressao.nomes(no) & (derivados.keys() | estados.keys())
        if estado.get("histerese", 0) > 0 and expressao.comparacao_do_topo(no) is None:
            erros.append((("estados", ident, "histerese"),
                          "a histerese só vale num «quando» que é uma comparação (<, <=, >, >=)"))
    ciclo = _ciclo(grafo)
    if ciclo:
        erros.append((caminho_do_no[ciclo[0]], f"ciclo: {' → '.join(ciclo)}"))

    for ident, efeito in efeitos.items():
        caminho = ("efeitos", ident)
        for campo in ("forca", "bpm"):
            if isinstance(efeito.get(campo), str):
                no = _expressao(efeito[campo], (*caminho, campo), erros, analisadas)
                if no is not None:
                    conferir_nomes(no, (*caminho, campo))
        cor = efeito.get("cor")
        if (isinstance(cor, str) and COR_DA_ENTRADA.match(cor)
                and entradas.get(cor[1:], {}).get("tipo") != "cor"):
            erros.append(((*caminho, "cor"), f"«{cor}» não é uma entrada de cor da receita"))

    for i, regra in enumerate(dados.get("regras", [])):
        caminho = ("regras", i)
        no = _expressao(regra["quando"], (*caminho, "quando"), erros, analisadas)
        if no is not None:
            conferir_nomes(no, (*caminho, "quando"))
        if isinstance(regra.get("espera_ms"), str):
            espera = _expressao(regra["espera_ms"], (*caminho, "espera_ms"), erros, analisadas)
            if espera is not None:
                conferir_nomes(espera, (*caminho, "espera_ms"))
        for parte in ("entao", "senao"):
            alvos = regra.get(parte, [])
            for j, alvo in enumerate([alvos] if isinstance(alvos, str) else alvos):
                onde = (*caminho, parte) if isinstance(alvos, str) else (*caminho, parte, j)
                if alvo not in efeitos:
                    erros.append((onde, f"o efeito «{alvo}» não existe"))
        if "para" in regra:
            de_controle = no is not None and any(
                sentidos.get(n, {}).get("especie") == "evento"
                and sentidos[n]["de"] in TOPICOS_POR_CONTROLE + universais.POR_CONTROLE
                for n in expressao.nomes(no))
            if regra["para"] == "quem_levou" and no is not None and not de_controle:
                erros.append(((*caminho, "para"), ("«quem_levou» pede um sentido de evento que "
                                                  "diga o controle (um tópico por controle)")))

    for i, confere in enumerate(dados.get("confere", [])):
        caminho = ("confere", i)
        if confere["sentido"] not in sentidos:
            erros.append(((*caminho, "sentido"), f"o sentido «{confere['sentido']}» não existe"))
        outro = confere.get("concorda_com")
        if outro is not None and (outro not in sentidos or outro == confere["sentido"]):
            erros.append(((*caminho, "concorda_com"), f"«{outro}» não é outro sentido da receita"))
        if "faixa" not in confere and outro is None:
            erros.append((caminho, "o confere pede «faixa» ou «concorda_com»"))
        if "tolerancia" in confere and outro is None:
            erros.append(((*caminho, "tolerancia"), "a tolerância é do «concorda_com»"))
        faixa = confere.get("faixa")
        if faixa and faixa[0] >= faixa[1]:
            erros.append(((*caminho, "faixa"), "a faixa pede a ponta de baixo antes da de cima"))

    return Receita(dados, analisadas, _ordem(grafo) if not ciclo else ())


def ler_receita(bruto: bytes | str) -> Receita:
    """A receita do texto, ou :class:`ReceitaRecusada` com a linha de cada erro."""
    dados_em_bytes = bruto.encode("utf-8") if isinstance(bruto, str) else bruto
    if len(dados_em_bytes) > TAMANHO_MAXIMO:
        linha = dados_em_bytes[:TAMANHO_MAXIMO].count(b"\n") + 1
        raise ReceitaRecusada([(linha, (f"a receita passa de {TAMANHO_MAXIMO // 1024} KB "
                                       f"({len(dados_em_bytes)} bytes)"))])
    try:
        texto = dados_em_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        linha = dados_em_bytes[:exc.start].count(b"\n") + 1
        raise ReceitaRecusada([(linha, "o texto não é UTF-8")]) from exc
    try:
        dados, linhas = ler(texto)
    except JsonRecusado as exc:
        raise ReceitaRecusada([(exc.linha, exc.mensagem)]) from exc
    erros: Erros = []
    RECEITA.conferir(dados, (), erros)
    receita = None
    if not erros:
        receita = _semantica(dados, erros)
    if erros or receita is None:
        vistos: set[tuple[int, str]] = set()
        saida = []
        for caminho, frase in erros:
            item = (linha_de(linhas, caminho), f"{_onde(caminho)}: {frase}")
            if item not in vistos:
                vistos.add(item)
                saida.append(item)
        raise ReceitaRecusada(saida)
    return receita
