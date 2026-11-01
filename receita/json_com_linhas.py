"""O JSON lido com a linha de cada chave e de cada valor, para o erro da receita apontar a linha.

O ``json`` da biblioteca padrão devolve só os valores; aqui cada caminho (as chaves e os índices
desde a raiz) guarda a linha em que nasce. A chave repetida recusa: no ``json`` ela some calada,
e a receita que a pessoa lê deixaria de ser a que o motor roda.
"""
from __future__ import annotations

import bisect
import re
from json.decoder import scanstring  # type: ignore[attr-defined]
from typing import Any

Caminho = tuple[str | int, ...]

_NUMERO = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_ESPACO = " \t\n\r"
_PROFUNDIDADE = 32
_PALAVRAS: dict[str, Any] = {"true": True, "false": False, "null": None}


class JsonRecusado(ValueError):
    """O texto não é JSON, com a linha (contada de 1) em que o defeito aparece."""

    def __init__(self, linha: int, mensagem: str) -> None:
        super().__init__(f"linha {linha}: {mensagem}")
        self.linha = linha
        self.mensagem = mensagem


class _Leitor:
    def __init__(self, texto: str) -> None:
        self.texto = texto
        self.i = 0
        self.quebras = [m.start() for m in re.finditer("\n", texto)]
        self.linhas: dict[Caminho, int] = {}

    def linha(self, posicao: int) -> int:
        return bisect.bisect_left(self.quebras, posicao) + 1

    def recusa(self, mensagem: str, posicao: int | None = None) -> JsonRecusado:
        return JsonRecusado(self.linha(self.i if posicao is None else posicao), mensagem)

    def pular_espaco(self) -> None:
        while self.i < len(self.texto) and self.texto[self.i] in _ESPACO:
            self.i += 1

    def valor(self, caminho: Caminho) -> Any:
        if len(caminho) > _PROFUNDIDADE:
            raise self.recusa(f"aninhado além de {_PROFUNDIDADE} níveis")
        self.pular_espaco()
        if self.i >= len(self.texto):
            raise self.recusa("o texto acabou antes do valor")
        self.linhas.setdefault(caminho, self.linha(self.i))
        letra = self.texto[self.i]
        if letra == "{":
            return self.objeto(caminho)
        if letra == "[":
            return self.lista(caminho)
        if letra == '"':
            return self.cadeia()
        for palavra, dado in _PALAVRAS.items():
            if self.texto.startswith(palavra, self.i):
                self.i += len(palavra)
                return dado
        achado = _NUMERO.match(self.texto, self.i)
        if achado is None:
            raise self.recusa(f"valor inesperado começando em «{letra}»")
        self.i = achado.end()
        bruto = achado.group()
        if any(c in bruto for c in ".eE"):
            return float(bruto)
        try:
            return int(bruto)
        except ValueError as exc:
            raise self.recusa(f"número de {len(bruto)} algarismos", achado.start()) from exc

    def cadeia(self) -> str:
        inicio = self.i
        try:
            texto, self.i = scanstring(self.texto, self.i + 1, True)
        except ValueError as exc:
            raise self.recusa("texto entre aspas sem fecho ou com escape torto", inicio) from exc
        return texto

    def objeto(self, caminho: Caminho) -> dict[str, Any]:
        self.i += 1
        saida: dict[str, Any] = {}
        self.pular_espaco()
        if self.texto.startswith("}", self.i):
            self.i += 1
            return saida
        while True:
            self.pular_espaco()
            if not self.texto.startswith('"', self.i):
                raise self.recusa("a chave tem de vir entre aspas")
            linha_da_chave = self.linha(self.i)
            chave = self.cadeia()
            if chave in saida:
                raise JsonRecusado(linha_da_chave, f"a chave «{chave}» aparece duas vezes")
            self.linhas[(*caminho, chave)] = linha_da_chave
            self.pular_espaco()
            if not self.texto.startswith(":", self.i):
                raise self.recusa(f"falta o «:» depois da chave «{chave}»")
            self.i += 1
            saida[chave] = self.valor((*caminho, chave))
            self.pular_espaco()
            if self.texto.startswith(",", self.i):
                self.i += 1
                continue
            if self.texto.startswith("}", self.i):
                self.i += 1
                return saida
            raise self.recusa("falta a vírgula ou o «}»")

    def lista(self, caminho: Caminho) -> list[Any]:
        self.i += 1
        saida: list[Any] = []
        self.pular_espaco()
        if self.texto.startswith("]", self.i):
            self.i += 1
            return saida
        while True:
            saida.append(self.valor((*caminho, len(saida))))
            self.pular_espaco()
            if self.texto.startswith(",", self.i):
                self.i += 1
                continue
            if self.texto.startswith("]", self.i):
                self.i += 1
                return saida
            raise self.recusa("falta a vírgula ou o «]»")


def ler(texto: str) -> tuple[Any, dict[Caminho, int]]:
    """O valor do texto JSON e a linha de cada caminho (a da chave, nos objetos)."""
    leitor = _Leitor(texto)
    dado = leitor.valor(())
    leitor.pular_espaco()
    if leitor.i != len(texto):
        raise leitor.recusa("sobra texto depois do fim do JSON")
    return dado, leitor.linhas


def linha_de(linhas: dict[Caminho, int], caminho: Caminho) -> int:
    """A linha do caminho, ou a do pai mais perto que tem linha (o campo que falta)."""
    while caminho not in linhas and caminho:
        caminho = caminho[:-1]
    return linhas.get(caminho, 1)
