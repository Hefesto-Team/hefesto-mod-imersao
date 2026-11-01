"""O motor com a porta de mentira: a ordem e o tempo dos efeitos, o mais forte, o teto e a queda.

O relógio é das provas: cada tique é ``k * 1000 / 60`` ms, e o evento entra no primeiro tique
que chega ao instante dele. As escritas ficam com o instante em que saíram.
"""
from __future__ import annotations

import asyncio
import itertools
import json
from collections.abc import Sequence
from typing import Any

import pytest
from apoio import DOIS, QUATRO_CONTROLES, UM, EscritasDeMentira, vibracao_do_jogo

from motor import efeitos
from motor.arbitragem import Pedido, decidir
from motor.laco import Motor, rodar
from motor.saida import TETO_POR_CONTROLE, TETO_TOTAL, Saida
from receita.formato import ler_receita

TIQUE = 1000 / 60
Evento = tuple[str, str, "str | None", dict[str, Any]]


def _motor(receita: dict[str, Any], controles: list[dict[str, Any]] | None = None,
           **porta: bool) -> tuple[Motor, Saida, EscritasDeMentira]:
    motor = Motor(ler_receita(json.dumps({"formato": 1, "motor": ">=1,<2", **receita})))
    motor.controles(controles if controles is not None else [{"uniq": UM, "jogador": 1}])
    escritas = EscritasDeMentira(**porta)
    return motor, Saida(escritas.pedir), escritas


def _correr(motor: Motor, saida: Saida, escritas: EscritasDeMentira, ate_ms: float,
            eventos: Sequence[tuple[float, Evento]] | None = None, de_ms: float = 0.0) -> None:
    fila = sorted(eventos or [], key=lambda e: e[0])

    async def correr() -> None:
        k = round(de_ms / TIQUE)
        while (t := k * TIQUE) <= ate_ms:
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            escritas.agora = t
            await saida.aplicar(t, motor.passo(t))
            k += 1

    asyncio.run(correr())


def _vib(forte: int) -> Evento:
    return ("jogo.vibracao", "jogo.vibracao", UM, vibracao_do_jogo(UM, forte))


def test_o_sentido_le_o_par_da_porta_pelo_indice_e_o_indice_que_falta_nao_vira_zero() -> None:
    motor, saida, escritas = _motor({
        "permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
        "sentidos": {"forte": {"de": "jogo.vibracao", "especie": "nivel", "campo": "pedido.1",
                               "escala": [0, 255]},
                     "fraco": {"de": "jogo.vibracao", "especie": "nivel", "campo": "efetivo.0",
                               "escala": [0, 255]}},
    })
    _correr(motor, saida, escritas, 100, [(0, _vib(255)), (50, ("jogo.vibracao", "jogo.vibracao",
                                                                UM, {"pedido": [], "efetivo": [51]}))])
    assert motor.leituras["forte"].valor == 1.0
    assert motor.leituras["fraco"].valor == pytest.approx(0.2)


def _perto(t: float, alvo: float) -> bool:
    return alvo <= t < alvo + TIQUE


def test_o_estado_que_sobe_e_desce_gera_os_efeitos_na_ordem_e_no_tempo() -> None:
    motor, saida, escritas = _motor({
        "permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
        "sentidos": {"tensao": {"de": "jogo.vibracao", "especie": "nivel", "campo": "pedido.1",  # (noqa-acento)
                                "escala": [0, 255]}},
        "estados": {"perigo": {"quando": "tensao > 0.5", "histerese": 0.1, "minimo_ms": 500}},  # (noqa-acento)
        "efeitos": {"pulso": {"canal": "motor", "forca": 0.8, "lado": "esquerdo"},
                    "alivio": {"canal": "luz", "cor": "#00ff00", "dura_ms": 300}},
        "regras": [{"quando": "perigo", "entao": "pulso", "senao": "alivio"}],
    })
    _correr(motor, saida, escritas, 1500, [
        (100, _vib(153)), (300, _vib(115)), (400, _vib(51)), (1000, _vib(200))])
    feitas = [(t, m, p.get("forte", p.get("rgb"))) for t, m, p in escritas.escritas]
    assert [(m, v) for _, m, v in feitas] == [
        ("vibracao.set", 204), ("luz.set", [0, 255, 0]), ("vibracao.set", 0),
        ("vibracao.set", 204)]
    assert _perto(feitas[0][0], 100), "o estado sobe no tique do evento"
    assert _perto(feitas[1][0], 600) and _perto(feitas[2][0], 600), \
        "abaixo da histerese aos 400 ms, o estado só desce aos 500 ms de ligado"
    assert _perto(feitas[3][0], 1000)
    assert escritas.de("luz.set")[0][1] == {"uniq": UM, "rgb": [0, 255, 0], "brilho": 1.0}


def _cruz(uniq: str = UM) -> Evento:
    return ("botoes", "button.down", uniq, {"botao": "cross"})


_CRUZ = {"permissoes": ["ler:botoes"],  # (noqa-acento)
         "sentidos": {"cruz": {"de": "botoes", "especie": "evento", "nome": "button.down",
                               "campo": "botao", "igual": "cross"}}}


def test_duas_regras_no_mesmo_canal_mandam_so_a_mais_forte_sem_somar() -> None:
    motor, saida, escritas = _motor({
        **_CRUZ,
        "efeitos": {"leve": {"canal": "motor", "forca": 0.3, "lado": "esquerdo", "dura_ms": 1000},
                    "forte": {"canal": "motor", "forca": 0.9, "lado": "esquerdo",
                              "dura_ms": 200}},
        "regras": [{"quando": "cruz", "entao": "leve", "prioridade": 9},
                   {"quando": "cruz", "entao": "forte"}],
    })
    _correr(motor, saida, escritas, 1300, [(0, _cruz())])
    fortes = [(t, p["forte"]) for t, p in escritas.de("vibracao.set")]
    assert [v for _, v in fortes] == [230, 76, 0], "0,9 vence; ao fim dele, a de 0,3; nunca 0,3+0,9"
    assert _perto(fortes[1][0], 200) and _perto(fortes[2][0], 1000)


def test_forca_igual_desempata_pela_prioridade_e_depois_pelo_mais_recente() -> None:
    motor, saida, escritas = _motor({
        **_CRUZ,
        "efeitos": {"vermelho": {"canal": "luz", "cor": "#ff0000", "dura_ms": 1000},
                    "azul": {"canal": "luz", "cor": "#0000ff", "dura_ms": 1000},
                    "verde": {"canal": "luz", "cor": "#00ff00", "dura_ms": 1000}},
        "regras": [{"quando": "cruz", "entao": "vermelho", "prioridade": 1},
                   {"quando": "cruz", "entao": "azul", "prioridade": 3},
                   {"quando": "cruz", "entao": "verde", "prioridade": 3, "espera_ms": 0}],
    })
    _correr(motor, saida, escritas, 100, [(0, _cruz())])
    assert [p["rgb"] for _, p in escritas.de("luz.set")] == [[0, 255, 0]]
    pedidos = [Pedido(UM, "luz", "-", n, 1.0, 3, t, i) for i, (n, t) in enumerate(
        (("velho", 0.0), ("novo", 50.0)))]
    assert decidir(pedidos)[(UM, "luz", "-")].efeito == "novo"
    assert decidir(reversed(pedidos))[(UM, "luz", "-")].efeito == "novo"


def test_o_teto_do_tato_vivo_segura_cada_controle_e_o_total() -> None:
    motor, saida, escritas = _motor({
        "permissoes": ["ler:entradas"],  # (noqa-acento)
        "sentidos": {"l2": {"de": "entradas", "especie": "nivel", "campo": "l2",
                            "escala": [0, 255]}},
        "efeitos": {"aperto": {"canal": "motor", "forca": "l2", "lado": "esquerdo"}},
        "regras": [{"quando": "l2 > 0", "entao": "aperto"}],
    }, QUATRO_CONTROLES)
    eventos = [(k * TIQUE, ("entradas", "controle.entradas", UM, {"l2": 1 + k % 200}))
               for k in range(150)]
    _correr(motor, saida, escritas, 3500, eventos)
    instantes = [(t, p["uniq"]) for t, p in escritas.de("vibracao.set")]
    for t0, _ in instantes:
        janela = [u for t, u in instantes if t0 <= t < t0 + 1000]
        assert len(janela) <= TETO_TOTAL
        assert all(janela.count(u) <= TETO_POR_CONTROLE for u in set(janela))
    assert max(sum(1 for t, _ in instantes if t0 <= t < t0 + 1000) for t0, _ in instantes) \
        == TETO_TOTAL, "a régua mede com o teto apertado"
    ultimo = {p["uniq"]: p["forte"] for _, p in escritas.de("vibracao.set")}
    assert set(ultimo.values()) == {round((1 + 149 % 200) / 255 * 255)}, \
        "o excesso espera, e o valor mais novo chega a todos"


_CORACAO = {
    "permissoes": ["ler:entradas"],  # (noqa-acento)
    "sentidos": {"l2": {"de": "entradas", "especie": "nivel", "campo": "l2",
                        "escala": [0, 255]}},
    "estados": {"apertado": {"quando": "l2 > 0.5"}},
    "efeitos": {"coracao": {"canal": "haptica", "padrao": "coracao", "forca": 1.0, "bpm": 60,  # (noqa-acento)
                            "lado": "esquerdo"}},
    "regras": [{"quando": "apertado", "entao": "coracao"}],  # (noqa-acento)
}


def _l2(valor: int) -> Evento:
    return ("entradas", "controle.entradas", UM, {"l2": valor})


def test_sem_haptica_na_porta_o_coracao_cai_no_motor_pelo_envelope() -> None:
    motor, saida, escritas = _motor(_CORACAO)
    _correr(motor, saida, escritas, 1080, [(0, _l2(255))])
    batidas = [(t, p["forte"]) for t, p in escritas.de("vibracao.set")]
    assert [v for _, v in batidas] == [255, 0, 178, 0, 255]
    assert [round(t / TIQUE) for t, _ in batidas] == [0, 6, 11, 18, 60]
    assert saida.sem_haptica


def test_o_coracao_que_cai_no_motor_disputa_o_motor_pelo_mais_forte_sem_somar() -> None:
    motor, saida, escritas = _motor({**_CORACAO, "efeitos": {
        "coracao": {"canal": "haptica", "padrao": "coracao", "forca": 0.5, "bpm": 60,  # (noqa-acento)
                    "lado": "esquerdo"},
        "fundo": {"canal": "motor", "forca": 0.4, "lado": "esquerdo"}},
        "regras": [{"quando": "apertado", "entao": ["coracao", "fundo"]}]})  # (noqa-acento)
    _correr(motor, saida, escritas, 1050, [(0, _l2(255))])
    assert [p["forte"] for _, p in escritas.de("vibracao.set")] == [128, 102, 128], \
        "a batida de 0,5 e o fundo de 0,4 dão 0,5; a segunda batida, de 0,35, perde para o fundo"


def test_com_haptica_na_porta_o_coracao_sai_pelo_padrao_e_solta_com_o_zero() -> None:
    motor, saida, escritas = _motor(_CORACAO, com_haptica=True)
    _correr(motor, saida, escritas, 1000, [(0, _l2(255)), (500, _l2(0))])
    toques = escritas.de("haptica.tocar")
    assert [(p["id"], p["forca"], p["bpm"]) for _, p in toques] == [
        ("coracao", 1.0, 60), ("coracao", 0.0, 60)]  # (noqa-acento)
    assert _perto(toques[1][0], 500)
    assert not escritas.de("vibracao.set")


def test_o_motor_que_segura_se_renova_antes_dos_tres_segundos_da_porta() -> None:
    motor, saida, escritas = _motor({**_CORACAO, "efeitos": {
        "coracao": {"canal": "motor", "forca": 0.5, "lado": "ambos"}}})  # (noqa-acento)
    _correr(motor, saida, escritas, 6000, [(0, _l2(255))])
    vezes = [t for t, p in escritas.de("vibracao.set")]
    assert [p for _, p in escritas.de("vibracao.set")] == [{"uniq": UM, "fraco": 128,
                                                            "forte": 128}] * 3
    assert all(0 < b - a < 3000 for a, b in itertools.pairwise(vezes))


def test_quem_levou_e_a_lista_de_jogadores_escolhem_o_controle() -> None:
    golpe = {"permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
             "sentidos": {"golpe": {"de": "jogo.vibracao", "especie": "evento", "campo": "pedido.1",
                                    "escala": [0, 255], "limiar": 0.5}},
             "efeitos": {"tranco": {"canal": "motor", "forca": 1.0, "dura_ms": 200}}}
    dois = [{"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}]
    for para, quem in (("quem_levou", {DOIS}), (["p1"], {UM}), ("todos", {UM, DOIS})):
        motor, saida, escritas = _motor(
            {**golpe, "regras": [{"quando": "golpe", "entao": "tranco", "para": para}]}, dois)
        _correr(motor, saida, escritas, 400,
                [(0, ("jogo.vibracao", "jogo.vibracao", DOIS,
                      vibracao_do_jogo(DOIS, 250, jogador=2)))])
        assert {p["uniq"] for _, p in escritas.de("vibracao.set")} == quem, para


def test_o_limiar_dispara_na_subida_e_a_espera_segura_o_repique() -> None:
    motor, saida, escritas = _motor({
        **_CRUZ,
        "efeitos": {"toque": {"canal": "motor", "forca": 1.0, "dura_ms": 50}},
        "regras": [{"quando": "cruz", "entao": "toque", "espera_ms": 400}],
    })
    _correr(motor, saida, escritas, 1100, [(k * 100.0, _cruz()) for k in range(10)])
    ligadas = [t for t, p in escritas.de("vibracao.set") if p["forte"]]
    assert [round(t / 100) * 100 for t in ligadas] == [0, 400, 800]


def test_o_acumulador_sobe_por_evento_e_cai_pela_meia_vida() -> None:
    motor, _saida, _escritas = _motor({
        **_CRUZ,
        "derivados": {"tensao": {"acumula": {"sobe_com": ["cruz"], "passo": 0.5,  # (noqa-acento)
                                             "meia_vida_ms": 1000}}},
        "estados": {"perigo": {"quando": "tensao > 0.7"}},  # (noqa-acento)
    })
    vistos: list[tuple[float, float, float]] = []

    async def correr() -> None:
        for k in range(120):
            t = k * TIQUE
            if k in (0, 6):
                motor.evento(*_cruz())
            motor.passo(t)
            vistos.append((t, motor.valores["tensao"], motor.valores["perigo"]))  # (noqa-acento)

    asyncio.run(correr())
    pico = max(v for _, v, _ in vistos)
    assert 0.95 < pico <= 1.0
    desceu = next(t for t, _, ligado in vistos[7:] if not ligado)
    assert 500 < desceu < 650, "0,97 cai a 0,7 em ~465 ms de meia-vida de 1 s"
    assert vistos[-1][1] == pytest.approx(pico * 0.5 ** ((vistos[-1][0] - 100) / 1000), 0.02)


def test_o_gatilho_sai_pelo_nome_do_trigger_set_e_solta_no_off() -> None:
    motor, saida, escritas = _motor({
        **_CRUZ,
        "efeitos": {"arma": {"canal": "gatilho", "modo": "arma", "lado": "r2", "inicio": 2,
                             "fim": 6, "forca": 8, "dura_ms": 300}},
        "regras": [{"quando": "cruz", "entao": "arma"}],
    })
    _correr(motor, saida, escritas, 500, [(0, _cruz())])
    assert [p for _, p in escritas.de("gatilho.set")] == [
        {"uniq": UM, "lado": "direito", "modo": "Weapon", "params": [2, 6, 255]},
        {"uniq": UM, "lado": "direito", "modo": "Off", "params": []}]


def test_o_coracao_e_o_susto_sao_padroes_pcm() -> None:
    taxa = 48_000
    coracao = efeitos.pcm("coracao", 1000, bpm=60)  # (noqa-acento)
    assert len(coracao) == taxa
    def amostra(a: int, b: int, onda: Any) -> Any:
        return onda[int(a * taxa / 1000):int(b * taxa / 1000)]

    assert max(map(abs, amostra(0, 90, coracao))) > 10_000
    assert max(map(abs, amostra(180, 290, coracao))) > 5_000
    assert not any(amostra(90, 180, coracao)) and not any(amostra(300, 1000, coracao))
    susto = efeitos.pcm("susto", 600)
    assert max(map(abs, amostra(0, 40, susto))) > 10_000 and not any(amostra(300, 600, susto))
    assert efeitos.envelope("susto", 500) == 0.0 and efeitos.envelope("coracao", 1000, 60) == 1.0  # (noqa-acento)


def test_o_laco_roda_perto_de_60_hz_e_solta_tudo_ao_parar() -> None:
    motor, saida, escritas = _motor({**_CORACAO, "efeitos": {
        "coracao": {"canal": "motor", "forca": 1.0}}})  # (noqa-acento)
    passos = 0
    original = motor.passo

    def contar(t_ms: float) -> Any:
        nonlocal passos
        passos += 1
        return original(t_ms)

    motor.passo = contar  # type: ignore[method-assign]

    async def correr() -> None:
        parar = asyncio.Event()
        motor.evento(*_l2(255))
        tarefa = asyncio.create_task(rodar(motor, saida, parar))
        await asyncio.sleep(0.5)
        parar.set()
        await asyncio.wait_for(tarefa, 2)

    asyncio.run(correr())
    assert 15 <= passos <= 40, passos
    assert [p["forte"] for _, p in escritas.de("vibracao.set")] == [255, 0]
