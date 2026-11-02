"""O Modo imersão usa a chave «Memória neste jogo», as linhas do «Agora» e o ``@presente``.

O ``jogo.memoria`` só chega ao motor com o ``memoria`` do ``perfil.trocou`` ligado, para qualquer
receita. O estado leva as linhas (os sentidos lendo, a memória que espera a chave e o último efeito,
com a hora) dentro do teto da porta, e os ``presentes`` da receita que vale, que mudam com ela e se
republicam. As opções de efeito da janela só aparecem com o nome que a receita publica.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, RAIZ, TRES, UM

import servidor
from motor.arbitragem import Pedido
from receita.biblioteca import Biblioteca
from receita.formato import Receita, ler_receita

DUNGEONS = "steam_app_1912410"
QUALQUER = "steam_app_900000004"
EFEITOS_DO_UNIVERSAL = {
    "coracao", "alivio", "golpe_com_lado", "lado_na_luz",  # (noqa-acento)
    "luz_do_dano", "cor_do_dano",
    "susto_no_alto_falante", "susto_no_tato", "intervalo_do_susto", "impacto_nos_gatilhos",
    "clima", "peso_da_mira"}


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"controles": []} if metodo == "controles.lista" else {}

    def estados(self) -> list[dict[str, Any]]:
        return [p for m, p in self.pedidos if m == "acessorios.estado"]


def _evento(topico: str, dados: dict[str, Any], nome: str | None = None) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": topico, "nome": nome or topico, "uniq": None,
                                           "dados": dados}}


def _trocou(jogo: str | None, memoria: bool) -> dict[str, Any]:
    return _evento("perfil.jogo", {"perfil": "Padrão", "jogo": jogo, "estilo": None,
                                   "controles": [], "memoria": memoria, "t": 1.0},
                   "perfil.trocou")


def _que_le_a_memoria() -> Receita:
    return ler_receita(json.dumps({
        "formato": 1, "motor": ">=1,<2", "jogo": {"chave": QUALQUER, "leitura_de_memoria": "pede"},
        "permissoes": ["ler:jogo.vibracao", "ler:jogo.memoria"],  # (noqa-acento)
        "entradas": {"tranco": {"rotulo": "Tranco", "tipo": "ligado", "padrao": True}},  # (noqa-acento)
        "sentidos": {
            "rumble": {"de": "jogo.vibracao", "especie": "nivel", "campo": "pedido.1",
                       "escala": [0, 255]},
            "vida_lida": {"de": "jogo.memoria", "especie": "nivel", "escala": [0, 100],
                          "leitura": {"tipo": "i32", "modulo": "jogo",  # (noqa-acento)
                                      "base": "0x40000"}}},
        "estados": {"vida_baixa": {"quando": "vida_lida < 0.3"}},
        "efeitos": {"tranco": {"canal": "motor", "forca": 1.0, "lado": "esquerdo"}},
        "regras": [{"quando": "rumble > 0.5", "entao": "tranco"},
                   {"quando": "vida_baixa", "entao": "tranco"}]}))


def _manifesto() -> dict[str, Any]:
    dado: dict[str, Any] = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    return dado


def _linha(estado: dict[str, Any], rotulo: str) -> str | None:
    return next((linha["valor"] for linha in estado["linhas"] if linha["rotulo"] == rotulo), None)


def _aceito(estado: dict[str, Any]) -> dict[str, Any]:
    porta_do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.porta")
    aceito: dict[str, Any] = porta_do_hefesto.estado_dos_acessorios(
        "imersao", estado, acoes_dos_aparelhos=frozenset({"ligar"}))
    return aceito


def test_a_memoria_chega_ao_motor_so_com_a_chave_do_hefesto_ligada() -> None:
    porta = _Porta()
    extensao = servidor.Extensao(porta, _que_le_a_memoria())  # type: ignore[arg-type]
    vistos: list[Any] = []
    extensao.motor.evento = lambda *a: vistos.append(a)  # type: ignore[method-assign]

    async def corpo() -> None:
        await extensao.ao_evento(_evento("jogo.memoria", {"vida_lida": 1}))
        await extensao.ao_evento(_trocou(QUALQUER, True))
        await extensao.ao_evento(_evento("jogo.memoria", {"vida_lida": 2}))
        await extensao.ao_evento(_trocou(QUALQUER, False))
        await extensao.ao_evento(_evento("jogo.memoria", {"vida_lida": 3}))
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": QUALQUER}))
        await extensao.ao_evento(_evento("jogo.memoria", {"vida_lida": 4}))

    asyncio.run(corpo())
    assert [v[3] for v in vistos if v[0] == "jogo.memoria"] == [{"vida_lida": 2}]


def test_o_estado_leva_as_linhas_no_teto_da_porta_e_os_presentes_da_receita() -> None:
    porta = _Porta()
    extensao = servidor.Extensao(porta, servidor.carregar_o_universal())  # type: ignore[arg-type]
    extensao.relogio = lambda: time.mktime((2026, 11, 2, 21, 4, 5, 0, 0, -1))

    async def corpo() -> None:
        await extensao.assinar()
        await extensao.publicar_o_estado()
        coracao = Pedido(UM, "haptica", "-", "coracao", 0.8, 0, 1000.0, 0)  # (noqa-acento)
        extensao.anotar({coracao.vaga: coracao})
        extensao.anotar({(UM, "luz", "-"): Pedido(UM, "luz", "-", "vermelho", 0.0, 0,
                                                  2000.0, 1)})
        await extensao.publicar_se_mudou()

    asyncio.run(corpo())
    antes, depois = porta.estados()
    assert _linha(antes, "Lendo") == "Som, vibração, microfone, parado, golpe"
    assert _linha(antes, "Último efeito") is None
    assert _linha(depois, "Último efeito") == "Coração, 21:04:05"
    for estado in (antes, depois):
        assert len(estado["linhas"]) <= servidor.TETO_DAS_LINHAS
        assert all(len(linha["rotulo"]) <= servidor.TETO_DO_ROTULO
                   and 0 < len(linha["valor"]) <= servidor.TETO_DO_VALOR
                   for linha in estado["linhas"])
        aceito = _aceito(estado)
        assert aceito["linhas"] == estado["linhas"]
        assert aceito["presentes"] == estado["presentes"]
    entradas = list(servidor.carregar_o_universal().secao("entradas"))
    assert depois["presentes"] == [*entradas, "canal.haptica", "canal.motor", "canal.gatilho",
                                   "canal.luz", "canal.som", "canal.leds", "canal.mira"]


def test_o_ultimo_efeito_sem_entrada_leva_o_nome_do_canal_e_o_antigo_nao_volta() -> None:
    extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal())  # type: ignore[arg-type]
    horas = iter((10.0, 20.0, 30.0))
    extensao.relogio = lambda: next(horas)
    extensao.anotar({(UM, "motor", "esquerdo"): Pedido(UM, "motor", "esquerdo", "motor_esquerdo",
                                                       0.5, 0, 500.0, 2)})
    assert extensao.ultimo_efeito == ("Motores", 10.0)
    extensao.anotar({(UM, "motor", "esquerdo"): Pedido(UM, "motor", "esquerdo", "motor_esquerdo",
                                                       0.5, 0, 500.0, 2)})
    assert extensao.ultimo_efeito == ("Motores", 10.0)
    extensao.anotar({(UM, "som", "-"): Pedido(UM, "som", "-", "susto_no_alto_falante", 1.0, 0,
                                              900.0, 3)})
    assert extensao.ultimo_efeito == ("Susto no alto-falante", 20.0)


def test_o_ultimo_efeito_vale_para_qualquer_controle_de_p1_a_p4() -> None:
    extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal())  # type: ignore[arg-type]
    extensao.relogio = lambda: 40.0
    controles = [UM, DOIS, TRES, QUATRO]
    pedidos = [Pedido(uniq, "haptica", "-", "coracao", 0.6, 0, 100.0 * n, 0)  # (noqa-acento)
               for n, uniq in enumerate(controles[:3], 1)]
    pedidos.append(Pedido(controles[3], "gatilho", "direito", "impacto_nos_gatilhos", 0.7, 0,
                          900.0, 4))
    extensao.anotar({p.vaga: p for p in pedidos})
    assert extensao.ultimo_efeito == ("Impacto nos gatilhos", 40.0)


def test_a_linha_dos_sentidos_cabe_no_valor_e_a_chave_desligada_sai_dela() -> None:
    assert servidor.lista_curta(["som", "vibração", "microfone", "parado", "tela", "golpe"]) == (
        "Som, vibração, microfone, parado, +2")
    for nomes in ([], ["som"], [n for _, n in servidor.NOMES_DOS_SENTIDOS]):
        assert len(servidor.lista_curta(nomes)) <= servidor.TETO_DO_VALOR
    extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal())  # type: ignore[arg-type]
    asyncio.run(extensao.assinar())
    assert "som" in extensao.sentidos_lendo()
    extensao.opcoes["sentido_som"] = False
    assert "som" not in extensao.sentidos_lendo()


def test_a_receita_que_le_a_memoria_diz_no_agora_que_espera_a_chave() -> None:
    porta = _Porta()
    extensao = servidor.Extensao(porta, _que_le_a_memoria())  # type: ignore[arg-type]

    async def corpo() -> None:
        await extensao.assinar()
        await extensao.publicar_o_estado()
        await extensao.ao_evento(_trocou(QUALQUER, False))
        await extensao.ao_evento(_trocou(QUALQUER, True))

    asyncio.run(corpo())
    fora, sem_chave, com_chave = porta.estados()
    assert _linha(fora, "Memória") is None
    assert _linha(sem_chave, "Memória") == servidor.ESPERA_A_MEMORIA == "Desligada"
    assert _linha(sem_chave, "Lendo") == "Vibração"
    assert _linha(com_chave, "Memória") is None
    assert _linha(com_chave, "Lendo") == "Vibração, memória"
    for estado in (fora, sem_chave, com_chave):
        assert _aceito(estado)["linhas"] == estado["linhas"]


def test_trocar_de_receita_muda_os_presentes_e_republica(tmp_path: Path) -> None:
    porta = _Porta()
    biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                            servidor.carregar_o_universal)
    extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                 biblioteca, tmp_path)

    async def corpo() -> None:
        await extensao.publicar_o_estado()
        await extensao.ao_evento(_trocou(DUNGEONS, False))
        await extensao.ao_evento(_trocou(None, False))

    asyncio.run(corpo())
    presentes = [e["presentes"] for e in porta.estados()]
    assert len(presentes) == 3
    assert "alivio" in presentes[0] and "alivio" not in presentes[1]
    assert presentes[2] == presentes[0]
    assert [e["perfil"] for e in porta.estados()][1] != porta.estados()[0]["perfil"]


def test_a_janela_mostra_so_o_efeito_que_a_receita_tem_e_a_chave_da_memoria() -> None:
    manifesto_do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto")
    opcoes_do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.opcoes")
    lido = manifesto_do_hefesto.ler_manifesto(RAIZ)
    memoria = [o for o in lido.opcoes if o.tipo == "memoria"]
    assert [(o.id, o.grupo, o.padrao) for o in memoria] == [("memoria", "Geral", None)]
    assert "linhas" in _manifesto()["agora"]
    padroes = {o["id"]: o["padrao"] for o in _manifesto()["opcoes"] if "padrao" in o}  # (noqa-acento)

    def efeitos(presentes: list[str], valores: dict[str, Any] = padroes) -> set[str]:
        return set(opcoes_do_hefesto.aparecem(lido, valores, presentes)) & EFEITOS_DO_UNIVERSAL

    universal = servidor.presentes_da_receita(servidor.carregar_o_universal())
    dungeons = servidor.presentes_da_receita(ler_receita(
        (RAIZ / "receitas" / "estudadas" / "minecraft-dungeons-ii.json").read_bytes()))
    assert efeitos(universal) == EFEITOS_DO_UNIVERSAL
    assert efeitos(dungeons) == EFEITOS_DO_UNIVERSAL - {"alivio"}
    assert efeitos([]) == set()
    assert efeitos([p for p in universal if p != "canal.mira"]) == EFEITOS_DO_UNIVERSAL - {
        "peso_da_mira"}
    for efeito in EFEITOS_DO_UNIVERSAL - {"peso_da_mira"}:
        assert efeito not in efeitos([p for p in universal if p != efeito]), efeito
    assert "cor_do_dano" not in efeitos(universal, {**padroes, "luz_do_dano": False})
    assert "memoria" in opcoes_do_hefesto.aparecem(lido, padroes, [])


def test_o_nome_de_cada_canal_no_agora_e_o_rotulo_da_chave_dele() -> None:
    rotulos = {o["id"]: o["rotulo"] for o in _manifesto()["opcoes"]}  # (noqa-acento)
    for canal, rotulo in servidor.ROTULOS_DOS_CANAIS.items():
        assert rotulos.get(f"canal_{canal}", rotulos["peso_da_mira"]) == rotulo
