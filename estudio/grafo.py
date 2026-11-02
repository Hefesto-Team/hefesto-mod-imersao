"""O grafo da receita: sentido → derivado → estado → regra → efeito, com o erro apontado no nó.

O grafo é a terceira vista do mesmo arquivo (as outras são os blocos e o texto). Cada nó guarda os
dados dele, e :func:`receita_do_grafo` devolve a receita igual, depois de normalizada. As arestas
saem dos dados: o nome lido numa expressão liga o dono dele a quem o lê, o ``sobe_com`` liga o
evento ao acumulador, e o ``entao``/``senao`` liga a regra aos efeitos. :func:`conferir` recusa,
apontando o nó, o grafo com mais de :data:`TETO_DE_NOS` nós ou :data:`TETO_DE_REGRAS` regras, o
ciclo, o nó órfão (sem aresta nenhuma nem lugar no ``confere``) e a aresta de tipo errado (a regra que faz um estado, a
expressão que lê um efeito ou um nome que não existe).
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from receita import expressao
from receita.formato import ReceitaRecusada, ler_receita

TETO_DE_NOS = 64
TETO_DE_REGRAS = 32
SECOES = (("entradas", "entrada"), ("sentidos", "sentido"), ("derivados", "derivado"),
          ("estados", "estado"), ("efeitos", "efeito"))
COLUNAS = {"entrada": 0, "sentido": 0, "derivado": 1, "estado": 2, "regra": 3, "efeito": 4}
LEEM_EXPRESSAO = {"sentido", "derivado", "estado", "entrada"}


@dataclass(frozen=True)
class No:
    """Um nó: ``tipo:nome`` (a regra é ``regra:<posição>``) e os dados dele na receita."""

    tipo: str
    nome: str
    dados: Any

    @property
    def id(self) -> str:
        return f"{self.tipo}:{self.nome}"


@dataclass(frozen=True)
class ErroNoNo:
    no: str
    frase: str


@dataclass
class Grafo:
    """Os nós, as arestas tiradas dos dados e o resto da receita (formato, jogo, permissões)."""

    nos: list[No]
    resto: dict[str, Any]
    secoes: list[str]
    arestas: list[tuple[str, str]] = field(default_factory=list)
    erradas: list[ErroNoNo] = field(default_factory=list)

    def para_a_pagina(self) -> dict[str, Any]:
        return {"nos": [{"id": n.id, "tipo": n.tipo, "nome": n.nome, "coluna": COLUNAS[n.tipo],
                         "dados": n.dados} for n in self.nos],
                "arestas": [list(a) for a in self.arestas]}


def _expressoes(no: No) -> list[str]:
    if no.tipo == "derivado" and isinstance(no.dados, dict) and "expr" in no.dados:
        return [str(no.dados["expr"])]
    if no.tipo in ("estado", "regra") and isinstance(no.dados, dict) and "quando" in no.dados:
        return [str(no.dados["quando"])]
    return []


def _efeitos_da_regra(dados: Any) -> list[str]:
    saida: list[str] = []
    for campo in ("entao", "senao"):
        valor = dados.get(campo, []) if isinstance(dados, dict) else []
        saida += [valor] if isinstance(valor, str) else [v for v in valor if isinstance(v, str)]
    return saida


def _ligar(grafo: Grafo) -> None:
    por_nome: dict[str, No] = {}
    for no in grafo.nos:
        if no.tipo in ("sentido", "derivado", "estado", "efeito"):
            por_nome.setdefault(no.nome, no)
    entradas = {n.nome: n for n in grafo.nos if n.tipo == "entrada"}
    arestas: list[tuple[str, str]] = []
    erradas: list[ErroNoNo] = []
    for no in grafo.nos:
        for texto in _expressoes(no):
            try:
                analisada = expressao.analisar(texto)
            except expressao.ExpressaoRecusada as exc:
                erradas.append(ErroNoNo(no.id, f"expressão recusada: {exc}"))
                continue
            for nome in sorted(expressao.nomes(analisada)):
                dono = por_nome.get(nome)
                if dono is None:
                    erradas.append(ErroNoNo(no.id, f"lê «{nome}», que não existe"))
                elif dono.tipo not in LEEM_EXPRESSAO:
                    erradas.append(ErroNoNo(no.id, f"lê «{nome}», que é {dono.tipo}"))
                else:
                    arestas.append((dono.id, no.id))
            for nome in sorted(expressao.entradas(analisada)):
                if nome in entradas:
                    arestas.append((entradas[nome].id, no.id))
                else:
                    erradas.append(ErroNoNo(no.id, f"lê a entrada «${nome}», que não existe"))
        if no.tipo == "derivado" and isinstance(no.dados, dict):
            for evento in no.dados.get("acumula", {}).get("sobe_com", []):
                dono = por_nome.get(evento)
                if dono is None or dono.tipo != "sentido":
                    erradas.append(ErroNoNo(no.id, f"sobe com «{evento}», que não é sentido"))
                else:
                    arestas.append((dono.id, no.id))
        if no.tipo == "regra":
            for efeito in _efeitos_da_regra(no.dados):
                dono = por_nome.get(efeito)
                if dono is None:
                    erradas.append(ErroNoNo(no.id, f"faz «{efeito}», que não existe"))
                elif dono.tipo != "efeito":
                    erradas.append(ErroNoNo(no.id, f"faz «{efeito}», que é {dono.tipo}"))
                else:
                    arestas.append((no.id, dono.id))
    grafo.arestas = list(dict.fromkeys(arestas))
    grafo.erradas = erradas


def grafo_da_receita(dados: dict[str, Any]) -> Grafo:
    """A receita como grafo; as seções que não viram nó ficam no ``resto``."""
    nos: list[No] = []
    for secao, tipo in SECOES:
        valor = dados.get(secao, {})
        if isinstance(valor, dict):
            nos += [No(tipo, nome, item) for nome, item in valor.items()]
    regras = dados.get("regras", [])
    if isinstance(regras, list):
        nos += [No("regra", str(i), regra) for i, regra in enumerate(regras)]
    nomes = {s for s, _ in SECOES} | {"regras"}
    grafo = Grafo(nos, {k: v for k, v in dados.items() if k not in nomes},
                  [k for k in dados if k in nomes])
    _ligar(grafo)
    return grafo


def receita_do_grafo(grafo: Grafo) -> dict[str, Any]:
    """O grafo de volta à receita."""
    dados = dict(grafo.resto)
    for secao, tipo in SECOES:
        do_tipo = {n.nome: n.dados for n in grafo.nos if n.tipo == tipo}
        if do_tipo or secao in grafo.secoes:
            dados[secao] = do_tipo
    regras = sorted((n for n in grafo.nos if n.tipo == "regra"), key=lambda n: int(n.nome))
    if regras or "regras" in grafo.secoes:
        dados["regras"] = [n.dados for n in regras]
    return dados


def _no_do_ciclo(grafo: Grafo) -> list[str] | None:
    vizinhos: dict[str, list[str]] = {}
    for de, para in grafo.arestas:
        vizinhos.setdefault(de, []).append(para)
    cor: dict[str, int] = {}
    pilha: list[str] = []

    def visitar(no: str) -> list[str] | None:
        cor[no] = 1
        pilha.append(no)
        for vizinho in vizinhos.get(no, []):
            if cor.get(vizinho) == 1:
                return pilha[pilha.index(vizinho):]
            if vizinho not in cor and (achado := visitar(vizinho)):
                return achado
        cor[no] = 2
        pilha.pop()
        return None

    for no in grafo.nos:
        if no.id not in cor and (achado := visitar(no.id)):
            return achado
    return None


def conferir(grafo: Grafo) -> list[ErroNoNo]:
    """Os erros do grafo, cada um no nó dele; vazio quando o grafo vale."""
    erros: list[ErroNoNo] = []
    if len(grafo.nos) > TETO_DE_NOS:
        erros.append(ErroNoNo(grafo.nos[TETO_DE_NOS].id,
                              f"passa de {TETO_DE_NOS} nós ({len(grafo.nos)})"))
    regras = [n for n in grafo.nos if n.tipo == "regra"]
    if len(regras) > TETO_DE_REGRAS:
        erros.append(ErroNoNo(regras[TETO_DE_REGRAS].id,
                              f"passa de {TETO_DE_REGRAS} regras ({len(regras)})"))
    erros += grafo.erradas
    ciclo = _no_do_ciclo(grafo)
    if ciclo:
        erros.append(ErroNoNo(ciclo[0], "ciclo: " + " → ".join([*ciclo, ciclo[0]])))
    ligados = {p for aresta in grafo.arestas for p in aresta}
    conferidos = {c.get(campo) for c in grafo.resto.get("confere", []) if isinstance(c, dict)
                  for campo in ("sentido", "concorda_com")}
    ligados |= {n.id for n in grafo.nos if n.tipo != "regra" and n.nome in conferidos}
    com_erro = {e.no for e in grafo.erradas}
    for no in grafo.nos:
        if no.id not in ligados and no.id not in com_erro and no.tipo != "entrada":
            erros.append(ErroNoNo(no.id, "nó órfão: nada o lê e ele não lê nada"))
    return erros


TIPOS_DO_EDITOR = ("grafo", "validar", "exportar", "importar")


def validar_o_texto(texto: str) -> list[dict[str, Any]]:
    """Os erros do texto da receita: os do formato com a linha, depois os do grafo com o nó."""
    try:
        receita = ler_receita(texto)
    except ReceitaRecusada as exc:
        return [{"linha": linha, "frase": frase} for linha, frase in exc.erros]
    return [{"no": e.no, "frase": e.frase} for e in conferir(grafo_da_receita(receita.dados))]


class Editor:
    """O grafo e o texto na página: ``grafo``, ``validar`` (a cada tecla), ``exportar`` e
    ``importar`` (que grava só o texto sem erro, em ``$HEFESTO_MOD_DADOS/receitas/<chave>.json``)."""

    def __init__(self, receitas: Path | None,
                 atual: Callable[[], tuple[str | None, dict[str, Any]]]) -> None:
        self.receitas = receitas
        self._atual = atual

    def mensagem(self, pedido: dict[str, Any]) -> dict[str, Any]:
        jogo, dados = self._atual()
        tipo = pedido.get("tipo")
        if tipo == "grafo":
            grafo = grafo_da_receita(dados)
            return {"tipo": "grafo", **grafo.para_a_pagina(),
                    "erros": [{"no": e.no, "frase": e.frase} for e in conferir(grafo)]}
        if tipo == "exportar":
            return {"tipo": "exportado", "nome": f"{jogo or 'universal'}.json",
                    "texto": json.dumps(dados, ensure_ascii=False, indent=2)}
        texto = pedido.get("texto")
        if not isinstance(texto, str):
            return {"tipo": "erro", "frase": "falta o texto da receita"}
        erros = validar_o_texto(texto)
        if tipo == "validar" or erros:
            return {"tipo": "validado", "erros": erros}
        if jogo is None or self.receitas is None:
            return {"tipo": "erro", "frase": "abra o jogo primeiro"}
        nova = json.loads(texto)
        nova["jogo"] = {**nova.get("jogo", {}), "chave": jogo}
        bruto = json.dumps(nova, ensure_ascii=False, indent=2).encode("utf-8")
        ler_receita(bruto)
        self.receitas.mkdir(parents=True, exist_ok=True)
        arquivo = self.receitas / f"{jogo}.json"
        temporario = arquivo.with_suffix(".json.novo")
        temporario.write_bytes(bruto)
        os.replace(temporario, arquivo)
        return {"tipo": "importado", "arquivo": arquivo.name}
