"""Os blocos QUANDO e FAÇA: a mesma receita vista de outro jeito, ida e volta sem perda.

A receita é a fonte; os blocos são a vista. Cada bloco é uma ``regra``: ``quando`` (a condição
sobre um estado ou sentido), ``faca`` (os efeitos da biblioteca da receita, o ``entao``), ``senao``,
``prioridade``, ``espera_ms`` e ``para`` (quem recebe). :func:`blocos_da_receita` monta a vista,
com a lista do QUANDO (estados, derivados e sentidos) e a do FAÇA (os efeitos, com a frase de cada
um como dica); :func:`receita_dos_blocos` devolve a receita, que sai igual byte a byte depois de
:func:`normalizar`.
"""
from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

CAMPOS_SOLTOS = ("prioridade", "espera_ms", "para")
LISTAS = (("entao", "faca"), ("senao", "senao"))
LADOS = {"esquerdo": "da esquerda", "direito": "da direita", "ambos": "dos dois lados"}
PARA = {"todos": "todos", "quem_levou": "quem levou"}


def normalizar(dados: Any) -> bytes:
    """A receita em bytes de uma forma só: chaves em ordem, sem espaço."""
    return json.dumps(dados, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _lista(valor: Any) -> list[str]:
    return [valor] if isinstance(valor, str) else list(valor)


def bloco_da_regra(regra: dict[str, Any]) -> dict[str, Any]:
    """Uma regra como bloco; ``texto`` lembra quais listas eram um nome só."""
    bloco: dict[str, Any] = {"quando": regra["quando"]}
    texto = []
    for campo, nome in LISTAS:
        if campo in regra:
            bloco[nome] = _lista(regra[campo])
            if isinstance(regra[campo], str):
                texto.append(campo)
    for campo in CAMPOS_SOLTOS:
        if campo in regra:
            bloco[campo] = regra[campo]
    if texto:
        bloco["texto"] = texto
    return bloco


def regra_do_bloco(bloco: dict[str, Any]) -> dict[str, Any]:
    """O bloco de volta à regra."""
    regra: dict[str, Any] = {"quando": bloco["quando"]}
    texto = set(bloco.get("texto", ()))
    for campo, nome in LISTAS:
        if nome in bloco:
            lista = list(bloco[nome])
            regra[campo] = lista[0] if campo in texto and len(lista) == 1 else lista
    for campo in CAMPOS_SOLTOS:
        if campo in bloco:
            regra[campo] = bloco[campo]
    return regra


def frase_do_efeito(efeito: dict[str, Any]) -> str:
    """A dica do efeito no FAÇA, em poucas palavras."""
    canal = efeito.get("canal")
    lado = LADOS.get(str(efeito.get("lado", "ambos")), "")
    forca = efeito.get("forca")
    em = f" a {round(forca * 100)}%" if isinstance(forca, (int, float)) else ""
    if canal == "motor":
        return f"vibra o motor {lado}{em}".strip()
    if canal == "haptica":
        return f"toca «{efeito.get('padrao')}» {lado}{em}".strip()  # (noqa-acento)
    if canal == "gatilho":
        return f"gatilho {efeito.get('lado', '')} em «{efeito.get('modo')}»".replace("  ", " ")
    if canal == "luz":
        return f"pinta a luz de {efeito.get('cor')}"
    if canal == "som":
        return f"toca o som «{efeito.get('som')}»"
    if canal == "leds":
        return f"acende as luzes de jogador {lado}".strip()
    return str(canal)


def opcoes_do_quando(dados: dict[str, Any]) -> list[dict[str, str]]:
    """O que o QUANDO lista: os estados, os derivados e os sentidos da receita."""
    return [{"nome": nome, "de": secao}
            for secao in ("estados", "derivados", "sentidos")
            for nome in dados.get(secao, {})]


def opcoes_do_faca(dados: dict[str, Any]) -> list[dict[str, str]]:
    """O que o FAÇA lista: os efeitos da receita, com a frase de cada um."""
    return [{"nome": nome, "dica": frase_do_efeito(efeito)}
            for nome, efeito in dados.get("efeitos", {}).items()]


def blocos_da_receita(dados: dict[str, Any]) -> dict[str, Any]:
    """A vista: a receita sem as regras, os blocos e as listas do QUANDO e do FAÇA."""
    return {"receita": {k: v for k, v in dados.items() if k != "regras"},
            "com_regras": "regras" in dados,
            "blocos": [bloco_da_regra(r) for r in dados.get("regras", [])],
            "quando": opcoes_do_quando(dados), "faca": opcoes_do_faca(dados)}


def receita_dos_blocos(vista: dict[str, Any]) -> dict[str, Any]:
    """A receita da vista; a ida e a volta saem iguais depois de :func:`normalizar`."""
    dados = dict(vista["receita"])
    blocos = vista.get("blocos", [])
    if blocos or vista.get("com_regras"):
        dados["regras"] = [regra_do_bloco(b) for b in blocos]
    return dados


TIPOS_DO_MONTADOR = ("blocos", "montar")


class Montador:
    """As mensagens dos blocos na página: ``blocos`` mostra a receita de agora e ``montar`` grava.

    ``montar`` só grava a receita que volta dos blocos depois de validada, em
    ``$HEFESTO_MOD_DADOS/receitas/<chave>.json``.
    """

    def __init__(self, receitas: Path | None, validar: Callable[[bytes], object],
                 atual: Callable[[], tuple[str | None, dict[str, Any]]]) -> None:
        self.receitas = receitas
        self._validar = validar
        self._atual = atual

    def mensagem(self, pedido: dict[str, Any]) -> dict[str, Any]:
        jogo, dados = self._atual()
        if pedido.get("tipo") == "blocos":
            return {"tipo": "blocos", "jogo": jogo, **blocos_da_receita(dados)}
        vista = pedido.get("vista")
        if jogo is None or self.receitas is None:
            return {"tipo": "erro", "frase": "abra o jogo primeiro"}
        if not isinstance(vista, dict) or not isinstance(vista.get("receita"), dict):
            return {"tipo": "erro", "frase": "blocos fora do formato"}
        try:
            nova = receita_dos_blocos(vista)
        except (KeyError, TypeError, IndexError):
            return {"tipo": "erro", "frase": "blocos fora do formato"}
        nova["jogo"] = {**nova.get("jogo", {}), "chave": jogo}
        bruto = json.dumps(nova, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            self._validar(bruto)
        except ValueError as exc:
            return {"tipo": "erro", "frase": f"a receita não fecha: {exc}"}
        self.receitas.mkdir(parents=True, exist_ok=True)
        arquivo = self.receitas / f"{jogo}.json"
        temporario = arquivo.with_suffix(".json.novo")
        temporario.write_bytes(bruto)
        with contextlib.suppress(OSError):
            os.replace(temporario, arquivo)
            return {"tipo": "montado", "arquivo": arquivo.name}
        return {"tipo": "erro", "frase": "não deu para gravar"}
