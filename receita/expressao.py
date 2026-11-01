"""As expressões da receita, sem ``eval``: um analisador que só conhece uma lista fechada.

A expressão vira uma árvore de nós, e o motor a percorre a cada tique. Fora da lista não há
caminho: nenhum atributo do Python, nenhuma chamada além das cinco funções, nenhum texto entre
aspas. O tamanho e o número de nós têm teto, e a árvore inteira se avalia em tempo fixo.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

TAMANHO_MAXIMO = 512
NOS_MAXIMOS = 64
PROFUNDIDADE_MAXIMA = 32

OPERADORES_DE_COMPARACAO = ("<=", ">=", "==", "!=", "<", ">")
PALAVRAS = ("e", "ou", "nao")  # (noqa-acento)
CAMPOS_DO_SENTIDO = ("lado", "forca", "jogador", "valor")
FUNCOES: dict[str, tuple[int, int]] = {
    "min": (2, 8),
    "max": (2, 8),
    "abs": (1, 1),
    "limita": (3, 3),
    "mapeia": (5, 5),
}

_FICHA = re.compile(
    r"\s*(?:(?P<num>[0-9]+(?:\.[0-9]+)?)"
    r"|(?P<entrada>\$[a-z][a-z0-9_]*)"
    r"|(?P<nome>[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)?)"
    r"|(?P<op><=|>=|==|!=|[-+*/<>(),]))"
)


class ExpressaoRecusada(ValueError):
    """A expressão fora da gramática, com a coluna (contada de 1) em que o defeito aparece."""

    def __init__(self, mensagem: str, coluna: int = 1) -> None:
        super().__init__(f"coluna {coluna}: {mensagem}")
        self.mensagem = mensagem
        self.coluna = coluna


@dataclass(frozen=True)
class Numero:
    valor: float


@dataclass(frozen=True)
class Nome:
    id: str
    campo: str | None = None


@dataclass(frozen=True)
class Entrada:
    id: str


@dataclass(frozen=True)
class Unario:
    op: str
    alvo: No


@dataclass(frozen=True)
class Binario:
    op: str
    esquerda: No
    direita: No


@dataclass(frozen=True)
class Chamada:
    funcao: str
    args: tuple[No, ...]


No = Numero | Nome | Entrada | Unario | Binario | Chamada


def _fichas(texto: str) -> list[tuple[str, str, int]]:
    saida: list[tuple[str, str, int]] = []
    i = 0
    while i < len(texto):
        if texto[i:].strip() == "":
            break
        achado = _FICHA.match(texto, i)
        if achado is None or achado.lastgroup is None:
            coluna = i + len(texto[i:]) - len(texto[i:].lstrip()) + 1
            raise ExpressaoRecusada(f"caractere fora da lista: «{texto[coluna - 1]}»", coluna)
        tipo = achado.lastgroup
        bruto = achado.group(tipo)
        saida.append((tipo, bruto, achado.start(tipo) + 1))
        i = achado.end()
    return saida


class _Analisador:
    def __init__(self, texto: str) -> None:
        self.fichas = _fichas(texto)
        self.i = 0
        self.nos = 0
        self.fundo = 0
        self.fim = len(texto) + 1

    def ver(self) -> tuple[str, str, int] | None:
        return self.fichas[self.i] if self.i < len(self.fichas) else None

    def coluna(self) -> int:
        ficha = self.ver()
        return ficha[2] if ficha else self.fim

    def e_palavra(self, palavra: str) -> bool:
        ficha = self.ver()
        return ficha is not None and ficha[0] == "nome" and ficha[1] == palavra

    def e_op(self, *ops: str) -> str | None:
        ficha = self.ver()
        if ficha is not None and ficha[0] == "op" and ficha[1] in ops:
            return ficha[1]
        return None

    def descer(self, coluna: int) -> None:
        self.fundo += 1
        if self.fundo > PROFUNDIDADE_MAXIMA:
            raise ExpressaoRecusada(f"mais de {PROFUNDIDADE_MAXIMA} níveis um dentro do outro",
                                    coluna)

    def contar(self, no: No) -> No:
        self.nos += 1
        if self.nos > NOS_MAXIMOS:
            raise ExpressaoRecusada(f"mais de {NOS_MAXIMOS} nós", self.coluna())
        return no

    def ou(self) -> No:
        no = self.e()
        while self.e_palavra("ou"):
            self.i += 1
            no = self.contar(Binario("ou", no, self.e()))
        return no

    def e(self) -> No:
        no = self.nao()
        while self.e_palavra("e"):
            self.i += 1
            no = self.contar(Binario("e", no, self.nao()))
        return no

    def nao(self) -> No:
        if self.e_palavra("nao"):  # (noqa-acento)
            self.descer(self.coluna())
            self.i += 1
            no = self.contar(Unario("nao", self.nao()))  # (noqa-acento)
            self.fundo -= 1
            return no
        return self.comparacao()

    def comparacao(self) -> No:
        no = self.soma()
        op = self.e_op(*OPERADORES_DE_COMPARACAO)
        if op:
            self.i += 1
            no = self.contar(Binario(op, no, self.soma()))
            if self.e_op(*OPERADORES_DE_COMPARACAO):
                raise ExpressaoRecusada("comparação encadeada: use «e»", self.coluna())
        return no

    def soma(self) -> No:
        no = self.produto()
        while op := self.e_op("+", "-"):
            self.i += 1
            no = self.contar(Binario(op, no, self.produto()))
        return no

    def produto(self) -> No:
        no = self.unario()
        while op := self.e_op("*", "/"):
            self.i += 1
            no = self.contar(Binario(op, no, self.unario()))
        return no

    def unario(self) -> No:
        if self.e_op("-"):
            self.descer(self.coluna())
            self.i += 1
            no = self.contar(Unario("-", self.unario()))
            self.fundo -= 1
            return no
        return self.atomo()

    def atomo(self) -> No:
        ficha = self.ver()
        if ficha is None:
            raise ExpressaoRecusada("a expressão acabou no meio", self.fim)
        tipo, bruto, coluna = ficha
        self.i += 1
        if tipo == "num":
            return self.contar(Numero(float(bruto)))
        if tipo == "entrada":
            return self.contar(Entrada(bruto[1:]))
        if tipo == "op" and bruto == "(":
            self.descer(coluna)
            no = self.ou()
            if not self.e_op(")"):
                raise ExpressaoRecusada("falta o «)»", self.coluna())
            self.i += 1
            self.fundo -= 1
            return no
        if tipo == "nome":
            return self.nome(bruto, coluna)
        raise ExpressaoRecusada(f"«{bruto}» fora do lugar", coluna)

    def nome(self, bruto: str, coluna: int) -> No:
        if bruto in PALAVRAS:
            raise ExpressaoRecusada(f"«{bruto}» fora do lugar", coluna)
        if self.e_op("("):
            if bruto not in FUNCOES:
                raise ExpressaoRecusada(f"função fora da lista: «{bruto}»", coluna)
            self.descer(coluna)
            self.i += 1
            args: list[No] = []
            if not self.e_op(")"):
                args.append(self.ou())
                while self.e_op(","):
                    self.i += 1
                    args.append(self.ou())
            if not self.e_op(")"):
                raise ExpressaoRecusada("falta o «)» da função", self.coluna())
            self.i += 1
            self.fundo -= 1
            minimo, maximo = FUNCOES[bruto]
            if not minimo <= len(args) <= maximo:
                raise ExpressaoRecusada(f"«{bruto}» pede de {minimo} a {maximo} valores", coluna)
            return self.contar(Chamada(bruto, tuple(args)))
        if bruto in FUNCOES:
            raise ExpressaoRecusada(f"«{bruto}» é função e pede parênteses", coluna)
        ident, _, campo = bruto.partition(".")
        if campo and campo not in CAMPOS_DO_SENTIDO:
            raise ExpressaoRecusada(
                f"campo «{campo}» fora da lista ({', '.join(CAMPOS_DO_SENTIDO)})", coluna)
        return self.contar(Nome(ident, campo or None))


def analisar(texto: str) -> No:
    """A árvore da expressão, ou :class:`ExpressaoRecusada` com a coluna do defeito."""
    if len(texto) > TAMANHO_MAXIMO:
        raise ExpressaoRecusada(f"mais de {TAMANHO_MAXIMO} letras")
    analisador = _Analisador(texto)
    if not analisador.fichas:
        raise ExpressaoRecusada("expressão vazia")
    no = analisador.ou()
    sobra = analisador.ver()
    if sobra is not None:
        raise ExpressaoRecusada(f"«{sobra[1]}» sobra depois da expressão", sobra[2])
    return no


def nomes(no: No) -> set[str]:
    """Os ids de sentido, derivado ou estado que a expressão lê."""
    if isinstance(no, Nome):
        return {no.id}
    if isinstance(no, Unario):
        return nomes(no.alvo)
    if isinstance(no, Binario):
        return nomes(no.esquerda) | nomes(no.direita)
    if isinstance(no, Chamada):
        return set().union(*(nomes(a) for a in no.args))
    return set()


def entradas(no: No) -> set[str]:
    """Os ids das entradas (``$id``) que a expressão lê."""
    if isinstance(no, Entrada):
        return {no.id}
    if isinstance(no, Unario):
        return entradas(no.alvo)
    if isinstance(no, Binario):
        return entradas(no.esquerda) | entradas(no.direita)
    if isinstance(no, Chamada):
        return set().union(*(entradas(a) for a in no.args))
    return set()


def comparacao_do_topo(no: No) -> Binario | None:
    """A comparação que é a expressão inteira (a única forma que aceita histerese)."""
    if isinstance(no, Binario) and no.op in ("<", "<=", ">", ">="):
        return no
    return None


LerNome = Callable[[str, "str | None"], float]
LerEntrada = Callable[[str], float]


def _verdade(valor: float) -> float:
    return 1.0 if valor != 0.0 else 0.0


def avaliar(no: No, ler_nome: LerNome, ler_entrada: LerEntrada) -> float:
    """O valor da árvore: número, e a verdade como 1 ou 0. Dividir por zero dá zero."""
    if isinstance(no, Numero):
        return no.valor
    if isinstance(no, Nome):
        return ler_nome(no.id, no.campo)
    if isinstance(no, Entrada):
        return ler_entrada(no.id)
    if isinstance(no, Unario):
        alvo = avaliar(no.alvo, ler_nome, ler_entrada)
        return 1.0 - _verdade(alvo) if no.op == "nao" else -alvo  # (noqa-acento)
    if isinstance(no, Binario):
        a = avaliar(no.esquerda, ler_nome, ler_entrada)
        if no.op == "e":
            return _verdade(a) * _verdade(avaliar(no.direita, ler_nome, ler_entrada))
        if no.op == "ou":
            return max(_verdade(a), _verdade(avaliar(no.direita, ler_nome, ler_entrada)))
        b = avaliar(no.direita, ler_nome, ler_entrada)
        return _BINARIOS[no.op](a, b)
    valores = [avaliar(a, ler_nome, ler_entrada) for a in no.args]
    return _FUNCOES[no.funcao](valores)


def _dividir(a: float, b: float) -> float:
    return a / b if b != 0.0 else 0.0


def _mapeia(v: list[float]) -> float:
    x, de_a, de_b, para_a, para_b = v
    if de_a == de_b:
        return para_a
    fracao = min(1.0, max(0.0, (x - de_a) / (de_b - de_a)))
    return para_a + fracao * (para_b - para_a)


_BINARIOS: dict[str, Callable[[float, float], float]] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": _dividir,
    "<": lambda a, b: float(a < b),
    "<=": lambda a, b: float(a <= b),
    ">": lambda a, b: float(a > b),
    ">=": lambda a, b: float(a >= b),
    "==": lambda a, b: float(a == b),
    "!=": lambda a, b: float(a != b),
}

_FUNCOES: dict[str, Callable[[list[float]], float]] = {
    "min": min,
    "max": max,
    "abs": lambda v: abs(v[0]),
    "limita": lambda v: min(max(v[0], v[1]), v[2]),
    "mapeia": _mapeia,
}
