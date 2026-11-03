"""A háptica registra os padrões do catálogo na porta antes do primeiro toque, e de novo quando a porta os perde.

Mordida: sem o ``haptica.registrar``, o Hefesto recusa todo ``haptica.tocar`` com «padrão não registrado», e o
coração e o susto nunca tocam.
"""
from __future__ import annotations

import asyncio

from apoio import UM, EscritasDeMentira

from motor import efeitos as catalogo
from motor.arbitragem import Pedido, Vaga
from motor.saida import Saida


def _coracao(t_ms: float) -> dict[Vaga, Pedido]:
    pedido = Pedido(UM, "haptica", "esquerdo", "coracao", 1.0, 0, t_ms, 0,  # (noqa-acento)
                    {"padrao": "coracao", "forca": 0.8, "bpm": 90.0, "inicio_ms": t_ms})  # (noqa-acento)
    return {pedido.vaga: pedido}


def test_o_primeiro_toque_vem_depois_do_registro_de_todo_o_catalogo() -> None:
    porta = EscritasDeMentira(com_haptica=True)
    saida = Saida(porta.pedir)
    asyncio.run(saida.aplicar(0.0, _coracao(0.0)))
    assert [n for n, _ in porta.registros] == [0] * len(catalogo.PADROES)
    assert {nome for _, nome in porta.registros} == set(catalogo.PADROES)
    assert [p["id"] for _, p in porta.de("haptica.tocar")] == ["coracao"]  # (noqa-acento)
    assert not saida.sem_haptica


def test_a_porta_que_perde_os_padroes_recebe_o_registro_de_novo() -> None:
    porta = EscritasDeMentira(com_haptica=True)
    saida = Saida(porta.pedir)
    asyncio.run(saida.aplicar(0.0, _coracao(0.0)))
    porta.esquecer()
    asyncio.run(saida.aplicar(5000.0, _coracao(5000.0)))
    asyncio.run(saida.aplicar(10000.0, _coracao(10000.0)))
    assert len(porta.registros) == 2 * len(catalogo.PADROES)
    assert len(porta.de("haptica.tocar")) == 2


def test_a_porta_sem_haptica_leva_o_padrao_ao_motor() -> None:
    porta = EscritasDeMentira(com_haptica=False)
    saida = Saida(porta.pedir)
    asyncio.run(saida.aplicar(0.0, _coracao(0.0)))
    assert saida.sem_haptica
    assert porta.de("haptica.tocar") == []
