"""O universal com sinais gravados: os efeitos certos, no canal e no lado certos, e o mais forte.

Cada prova é uma linha do tempo sintética dos tópicos que a porta entrega (``jogo.som``,
``jogo.vibracao``, ``microfone.nivel``, ``entradas``, ``movimento``, ``jogo.haptica`` e
``jogo.gatilho``), corrida tique a tique no relógio das provas. O tato vivo de mentira guarda o
nível que o jogo pede em cada canal e recusa com ``-32011`` o pedido que não passa dele, como a
regra do mais forte da porta.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import pytest
from apoio import DOIS, QUATRO, QUATRO_CONTROLES, TRES, UM, EscritasDeMentira, Recusa
from apoio import vibracao_do_jogo as vibracao

import servidor
from motor.laco import Motor
from motor.saida import Saida
from receita.formato import TOPICOS_DOS_SENTIDOS, ReceitaRecusada, ler_receita
from sentidos.quietude import Quietude
from sentidos.rumble import Rumble

TIQUE = 1000 / 60
Evento = tuple[str, str, "str | None", dict[str, Any]]


def som(lado: Any, energia: float, t_s: float) -> Evento:
    return ("jogo.som", "jogo.som", None, {"t": t_s, "evento": "estalo", "lado": lado,
                                           "energia": energia, "canais": 2, "bandas": [0.0] * 24})


def microfone(uniq: str, nivel: float, mudo: bool = False) -> Evento:
    return ("microfone.nivel", "microfone.nivel", uniq,
            {"uniq": uniq, "nivel": nivel, "mudo": mudo, "do_jogo": False, "t": 0.0})


def rumble(uniq: str, forte: int, fraco: int = 0) -> Evento:
    return ("jogo.vibracao", "jogo.vibracao", uniq, vibracao(uniq, forte, fraco))


def entradas(uniq: str, r2: int, l2: int = 0, transporte: str = "usb") -> Evento:
    return ("entradas", "controle.entradas", uniq, {
        "uniq": uniq, "jogador": 1, "transporte": transporte, "lx": 128, "ly": 128, "rx": 128,
        "ry": 128, "l2": l2, "r2": r2, "dedos": []})


def giro(uniq: str, z: float) -> Evento:
    return ("movimento", "controle.movimento", uniq, {
        "uniq": uniq, "transporte": "bt", "giro": {"x": 0.0, "y": 0.0, "z": z},
        "acel": {"x": 0.0, "y": 0.0, "z": 1.0}})


def na_mao(uniq: str, ate_ms: int) -> list[tuple[float, Evento]]:
    return [(t, giro(uniq, 3.0)) for t in range(0, ate_ms, 400)]


def haptica_do_jogo(uniq: str, esq: float, dir_: float) -> Evento:
    return ("jogo.haptica", "jogo.haptica", uniq,
            {"uniq": uniq, "jogador": 1, "intensidade": [esq, dir_], "t": 0.0})


def gatilho_do_jogo(uniq: str, lado: str, modo: str, forca: float) -> Evento:
    return ("jogo.gatilho", "jogo.gatilho", uniq, {"uniq": uniq, "jogador": 1, "lado": lado,
                                                   "modo": modo, "forca": forca,
                                                   "posicao": 0.2, "t": 0.0})


def _forca_do_trigger(modo: str, params: list[int]) -> float:
    if modo == "Off" or not params:
        return 0.0
    if modo in ("Feedback", "Vibration"):
        return params[1] / 8
    return max(params) / 8


class TatoVivoDeMentira(EscritasDeMentira):
    """A porta com a regra do mais forte: o pedido que não passa do jogo recebe o ``-32011``."""

    def __init__(self, **porta: bool) -> None:
        super().__init__(**porta)
        self.jogo: dict[tuple[str, str, str], float] = {}
        self.recusas: list[tuple[float, str, dict[str, Any]]] = []

    def ver(self, evento: Evento) -> None:
        topico, _, uniq, dados = evento
        if uniq is None:
            return
        if topico == "jogo.haptica":
            for lado, valor in zip(("esquerdo", "direito"), dados["intensidade"]):
                self.jogo[(uniq, "haptica", lado)] = float(valor)
        elif topico == "jogo.gatilho":
            forca = 0.0 if dados["modo"] == "desligado" else float(dados["forca"])
            self.jogo[(uniq, "gatilho", dados["lado"])] = forca

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        uniq = params.get("uniq", "")
        if metodo == "haptica.tocar":
            vaga, forca = (uniq, "haptica", params["lado"]), float(params["forca"])
        elif metodo == "gatilho.set":
            vaga, forca = (uniq, "gatilho", params["lado"]), _forca_do_trigger(
                params["modo"], params["params"])
        else:
            return await super().pedir(metodo, params)
        if forca > 0 and forca <= self.jogo.get(vaga, 0.0):
            self.recusas.append((self.agora, metodo, dict(params)))
            raise Recusa("mais fraco que o pedido vivo no canal", -32011)
        return await super().pedir(metodo, params)


def _universal(controles: list[dict[str, Any]] | None = None,
               opcoes: dict[str, Any] | None = None) -> Motor:
    motor = Motor(servidor.carregar_o_universal(), opcoes)
    motor.controles(controles if controles is not None else [{"uniq": UM, "jogador": 1}])
    return motor


def _correr(motor: Motor, porta: EscritasDeMentira, ate_ms: float,
            eventos: Sequence[tuple[float, Evento]] = ()) -> tuple[Saida, list[str]]:
    fila = sorted(eventos, key=lambda e: e[0])
    diario: list[str] = []
    saida = Saida(porta.pedir, diario.append)

    async def correr() -> None:
        k = 0
        while (t := k * TIQUE) <= ate_ms:
            while fila and fila[0][0] <= t + 1e-6:
                evento = fila.pop(0)[1]
                if isinstance(porta, TatoVivoDeMentira):
                    porta.ver(evento)
                motor.evento(*evento)
            porta.agora = t
            await saida.aplicar(t, motor.passo(t))
            k += 1

    asyncio.run(correr())
    return saida, diario


def _motores(porta: EscritasDeMentira, uniq: str = UM) -> list[tuple[float, int, int]]:
    return [(t, p["forte"], p["fraco"]) for t, p in porta.de("vibracao.set") if p["uniq"] == uniq]


def test_o_universal_vale_no_formato_1_le_os_seis_sentidos_e_nasce_sem_o_lado_na_luz() -> None:
    receita = servidor.carregar_o_universal()
    assert receita.universal and not receita.vazia
    lidos = {s["de"] for s in receita.secao("sentidos").values()}
    assert lidos == set(TOPICOS_DOS_SENTIDOS)
    assert receita.secao("entradas")["lado_na_luz"]["padrao"] is False  # (noqa-acento)
    assert "jogo" not in receita.dados
    bruto = json.loads(servidor.ARQUIVO_DO_UNIVERSAL.read_text(encoding="utf-8"))
    assert ler_receita(json.dumps(bruto)).dados == receita.dados


def test_o_estalo_forte_da_esquerda_vibra_a_esquerda_e_o_da_direita_a_direita() -> None:
    motor, porta = _universal(), EscritasDeMentira()
    _correr(motor, porta, 1500, [(200, som("esquerdo", 0.4, 0.2)), (900, som(0.8, 0.4, 0.9)),
                                 (1300, som("esquerdo", 0.1, 1.3))])
    motores = _motores(porta)
    esquerdo = [m for m in motores if 200 <= m[0] < 400 and m[1]]
    direito = [m for m in motores if 900 <= m[0] < 1100 and m[2]]
    assert esquerdo and all(f == 0 for _, _, f in esquerdo)
    assert direito and all(f == 0 for _, f, _ in direito)
    assert esquerdo[0][1] == round(0.7 * 255) and direito[0][2] == round(0.7 * 255)
    assert not [m for m in motores if m[0] >= 1300 and (m[1] or m[2])]
    assert not porta.de("leds.set") and not porta.de("luz.set")


def test_o_lado_na_luz_ligado_acende_as_luzes_de_jogador_do_lado_por_ate_600_ms() -> None:
    motor, porta = _universal(opcoes={"lado_na_luz": True}), EscritasDeMentira()
    _correr(motor, porta, 1500, [(200, som("esquerdo", 0.4, 0.2)), (900, som(0.8, 0.4, 0.9))])
    assert [(p["mascara"], p["ate_ms"]) for _, p in porta.de("leds.set")] == [
        (0b00011, 600), (0b11000, 600)]
    assert [round(t) for t, _ in porta.de("leds.set")] == [200, 900]


def test_o_silencio_longo_acelera_o_coracao_e_o_barulho_subito_o_acalma() -> None:
    motor, porta = _universal(), EscritasDeMentira(com_haptica=True)
    linha = [(t, microfone(UM, 0.01)) for t in range(0, 36_000, 500)] + na_mao(UM, 42_000)
    linha += [(36_000, microfone(UM, 0.8)), (36_500, microfone(UM, 0.02))]
    _correr(motor, porta, 42_000, linha)
    coracao = [(t, p["bpm"], p["forca"]) for t, p in porta.de("haptica.tocar")
               if p["id"] == "coracao" and p["forca"] > 0]  # (noqa-acento)
    assert coracao and 11_000 < coracao[0][0] < 14_000
    cedo = [b for t, b, _ in coracao if t < 16_000]
    tarde = [b for t, b, _ in coracao if 30_000 < t < 36_000]
    assert max(cedo) < min(tarde) and 100 <= max(tarde) <= 140
    calmo = [(t, b, f) for t, b, f in coracao if t > 36_000]
    assert calmo and calmo[-1][1:] == (60, 0.25)


def test_o_controle_largado_na_mesa_com_silencio_nao_liga_o_coracao() -> None:
    silencio = [(t, microfone(UM, 0.01)) for t in range(0, 40_000, 500)]
    coracoes = {}
    for nome, mao in (("na_mesa", []), ("na_mao", na_mao(UM, 40_000))):
        motor, porta = _universal(), EscritasDeMentira(com_haptica=True)
        _correr(motor, porta, 40_000, silencio + mao)
        coracoes[nome] = [t for t, p in porta.de("haptica.tocar") if p["forca"] > 0]  # (noqa-acento)
    assert coracoes["na_mao"] and not coracoes["na_mesa"]


def test_a_rajada_de_rumble_pinta_de_vermelho_so_o_controle_que_levou_de_p1_a_p4() -> None:
    motor, porta = _universal(QUATRO_CONTROLES), EscritasDeMentira()
    linha = [(t, rumble(TRES, 230)) for t in (1000, 1100, 1200, 1300, 1400)]
    linha += [(1500, rumble(TRES, 0)), (2000, som("direito", 0.5, 2.0))]
    _correr(motor, porta, 2600, linha)
    assert {p["uniq"] for _, p in porta.de("luz.set")} == {TRES}
    assert porta.de("luz.set")[0][1]["rgb"] == [255, 0, 0]
    assert {u for u in (UM, DOIS, TRES, QUATRO) if any(f for t, _, f in _motores(porta, u)
                                                        if t >= 2000)} == {UM, DOIS, TRES, QUATRO}


def test_o_rumble_se_separa_em_pulso_rajada_e_batimento() -> None:
    sentido, eventos = Rumble(), []
    linha: list[tuple[float, int]] = [(0, 200), (100, 0), (1000, 230), (1250, 230), (1500, 0)]
    linha += [(t, v) for b in (3000, 3800, 4600) for t, v in ((b, 120), (b + 80, 0))]
    for t, forte in linha:
        eventos += sentido.ler("jogo.vibracao", "jogo.vibracao", UM, vibracao(UM, forte), t)
        eventos += sentido.tique(t + 1, [UM], frozenset())
    nomes = [e.nome for e in eventos if e.nome != "nivel"]
    assert nomes == ["pulso", "rajada", "pulso", "pulso", "batimento", "pulso"]
    niveis = [e.dados for e in eventos if e.nome == "nivel"]
    assert niveis[-1]["tensao"] > 0.9 and niveis[-1]["dano_recente"] > 0.2


def test_o_golpe_dado_pede_o_impacto_no_gatilho_que_atacou_so_no_controle_que_atacou() -> None:
    motor, porta = _universal([{"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}]), (
        EscritasDeMentira())
    _correr(motor, porta, 2000, [
        (100, entradas(UM, 200, transporte="bt")), (200, rumble(UM, 180)), (300, rumble(UM, 0)),
        (1000, entradas(DOIS, 200)), (1400, rumble(DOIS, 180)), (1500, rumble(DOIS, 0)),
    ])
    gatilhos = [(round(t), p["uniq"], p["lado"], p["modo"]) for t, p in porta.de("gatilho.set")]
    assert gatilhos[0] == (200, UM, "direito", "Vibration")
    assert gatilhos[1][1:] == (UM, "direito", "Off") and 340 <= gatilhos[1][0] <= 370
    assert not [g for g in gatilhos if g[1] == DOIS]


def test_a_haptica_do_jogo_mais_forte_cala_o_coracao_e_a_mais_fraca_deixa_ele_nas_brechas() -> None:
    linha = [(t, microfone(UM, 0.01)) for t in range(0, 30_000, 500)] + na_mao(UM, 30_000)
    forte: list[tuple[float, Evento]] = [
        (t, haptica_do_jogo(UM, 0.9, 0.9)) for t in range(20_000, 30_000, 250)]
    fraca: list[tuple[float, Evento]] = [
        (t, haptica_do_jogo(UM, 0.1, 0.1)) for t in range(20_000, 30_000, 250)]
    resultados = {}
    for nome, jogo in (("forte", forte), ("fraca", fraca)):
        motor, porta = _universal(), TatoVivoDeMentira(com_haptica=True)
        _correr(motor, porta, 30_000, linha + jogo)
        resultados[nome] = [p for t, p in porta.de("haptica.tocar")
                            if t >= 20_100 and p["id"] == "coracao" and p["forca"] > 0]  # (noqa-acento)
    assert not resultados["forte"]
    assert resultados["fraca"] and {p["lado"] for p in resultados["fraca"]} == {
        "esquerdo", "direito"}


def test_o_impacto_do_golpe_so_troca_o_gatilho_quando_passa_do_gatilho_do_jogo() -> None:
    golpe = [(1000, entradas(UM, 200)), (1080, rumble(UM, 180)), (1200, rumble(UM, 0))]
    aceitos = {}
    for forca in (0.5, 1.0):
        motor, porta = _universal(), TatoVivoDeMentira()
        _correr(motor, porta, 1600, [(500, gatilho_do_jogo(UM, "direito", "arma", forca)),
                                     *golpe])
        aceitos[forca] = [p for _, p in porta.de("gatilho.set") if p["modo"] != "Off"]
    assert [p["modo"] for p in aceitos[0.5]] == ["Vibration"]
    assert not aceitos[1.0]


def test_o_giro_gravado_com_o_motor_ligado_nao_conta_como_se_mexeu() -> None:
    def correr(vibra: bool) -> list[str]:
        sentido, nomes = Quietude(), []
        for t in range(0, 3000, 50):
            if vibra and 1000 <= t < 2000 and t % 250 == 0:
                sentido.ler("jogo.vibracao", "jogo.vibracao", UM, vibracao(UM, 200), t)
            if vibra and t == 2000:
                sentido.ler("jogo.vibracao", "jogo.vibracao", UM, vibracao(UM, 0), t)
            if 1050 <= t < 2050:
                nomes += [e.nome for e in sentido.ler("movimento", "controle.movimento", UM,
                                                      giro(UM, 40.0)[3], t)]
            nomes += [e.nome for e in sentido.tique(t, [UM], frozenset())]
        return [n for n in nomes if n != "nivel"]

    assert correr(vibra=True) == []
    assert correr(vibra=False) and set(correr(vibra=False)) == {"mexeu"}


def test_a_propria_saida_da_extensao_tambem_cala_o_giro() -> None:
    sentido = Quietude()
    sentido.tique(0, [UM], frozenset({UM}))
    assert not sentido.ler("movimento", "controle.movimento", UM, giro(UM, 40.0)[3], 50)
    sentido.tique(200, [UM], frozenset())
    assert [e.nome for e in sentido.ler("movimento", "controle.movimento", UM,
                                        giro(UM, 40.0)[3], 250)] == ["mexeu"]


@pytest.mark.parametrize("com_haptica", [True, False])
def test_o_coracao_que_a_extensao_toca_nao_cega_o_giro_entre_os_golpes(com_haptica: bool) -> None:
    linha = [(t, rumble(UM, v)) for b in (1000, 1800, 2600, 3400) for t, v in ((b, 120), (b + 80, 0))]
    linha += [(t, giro(UM, 40.0)) for t in range(0, 30_000, 33) if not 500 <= t < 1200]
    motor, porta = _universal(), EscritasDeMentira(com_haptica=com_haptica)
    _correr(motor, porta, 30_000, linha)
    if com_haptica:
        coracao = [t for t, p in porta.de("haptica.tocar") if p["forca"] > 0]  # (noqa-acento)
    else:
        coracao = [t for t, p in porta.de("vibracao.set") if p["forte"] or p["fraco"]]
    assert coracao and coracao[0] < 4000
    assert coracao[-1] < 16_000


def test_o_susto_toca_o_recorte_do_proprio_jogo_pelo_t_do_estalo_e_cala_sem_o_som() -> None:
    linha = [(t, microfone(UM, 0.01)) for t in range(0, 20_000, 500)] + na_mao(UM, 20_000)
    linha += [(18_000, som("direito", 0.45, 1234.5))]
    motor, porta = _universal(), EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(motor, porta, 19_000, linha)
    assert [p for _, p in porta.de("som.tocar")] == [
        {"uniq": UM, "som": "recorte", "volume": 1.0, "t": 1234.5}]
    assert [p["id"] for _, p in porta.de("haptica.tocar")  # (noqa-acento)
            if p["id"] == "susto"]  # (noqa-acento)
    motor, porta = _universal(), EscritasDeMentira(com_haptica=True)
    saida, diario = _correr(motor, porta, 19_000, linha)
    assert not porta.de("som.tocar") and saida.sem_som
    assert "a porta não toca som: o efeito de som fica calado" in diario


def test_sem_a_porta_das_luzes_de_jogador_o_lado_na_luz_se_cala_e_o_motor_segue() -> None:
    class SemLeds(EscritasDeMentira):
        async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
            if metodo == "leds.set":
                raise Recusa("método desconhecido: leds.set", -32601)
            return await super().pedir(metodo, params)

    motor, porta = _universal(opcoes={"lado_na_luz": True}), SemLeds()
    saida, _ = _correr(motor, porta, 1500, [(200, som("esquerdo", 0.4, 0.2)),
                                            (900, som("esquerdo", 0.4, 0.9))])
    assert saida.sem_leds and not porta.de("leds.set")
    assert len([m for m in _motores(porta) if m[1]]) == 2


def test_ler_um_sentido_universal_pede_a_permissao_de_cada_origem_dele() -> None:
    permissoes = ["ler:botoes", "ler:jogo.vibracao"]  # (noqa-acento)
    receita = {"formato": 1, "motor": ">=1,<2", "permissoes": permissoes,  # (noqa-acento)
               "sentidos": {"golpe": {"de": "sentido.golpe", "especie": "evento", "nome": "dado"}}}
    with pytest.raises(ReceitaRecusada, match="sem declarar «ler:entradas»"):
        ler_receita(json.dumps(receita))
    permissoes.append("ler:entradas")
    assert ler_receita(json.dumps(receita)).secao("sentidos")["golpe"]["de"] == "sentido.golpe"


def test_as_luzes_de_jogador_nunca_passam_de_600_ms() -> None:
    efeito = {"canal": "leds", "lado": "esquerdo", "dura_ms": 601}
    with pytest.raises(ReceitaRecusada, match="601 fora da faixa de 1 a 600"):
        ler_receita(json.dumps({"formato": 1, "motor": ">=1,<2", "efeitos": {"luzes": efeito}}))
