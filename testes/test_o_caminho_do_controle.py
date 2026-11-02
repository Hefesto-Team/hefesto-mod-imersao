"""O caminho do controle do jogo medido ao vivo: a vaga que o jogo ocupa e o mais forte nela.

As linhas do tempo são as três formas do jogo sob o Proton: só os motores (o XInput), os motores
com a luz e o gatilho (o hidraw Sony) e a háptica (o áudio do controle). A porta de mentira não
arbitra o motor, o gatilho nem a háptica: quem decide ali é o motor, pelo que o jogo escreveu. A
luz do jogo não tem tópico, e a porta recusa com ``-32011`` a luz mais fraca que a do jogo.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any, cast

import pytest
from apoio import DOIS, QUATRO, QUATRO_CONTROLES, TRES, UM, EscritasDeMentira, Recusa
from apoio import vibracao_do_jogo as vibracao

import servidor
from motor.caminho import JANELA_MS, SEM_BATIDA_MS
from motor.laco import Motor
from motor.saida import Saida
from receita.formato import ler_receita

TIQUE = 1000 / 60
BATIDA_MS = 250
Evento = tuple[str, str, "str | None", dict[str, Any]]
EFEITOS = {
    "motor": {"canal": "motor", "lado": "ambos", "forca": 0.5},
    "luz": {"canal": "luz", "cor": "#ff0000", "brilho": 0.5},
    "gatilho": {"canal": "gatilho", "lado": "ambos", "modo": "resistencia", "posicao": 2,  # (noqa-acento)
                "forca": 4},
    "coracao": {"canal": "haptica", "padrao": "coracao", "forca": 0.5},  # (noqa-acento)
}


def _receita(*efeitos: str) -> Any:
    return ler_receita(json.dumps({
        "formato": 1, "motor": ">=1,<2",
        "entradas": {"sempre": {"tipo": "ligado", "rotulo": "Sempre", "padrao": True}},  # (noqa-acento)
        "efeitos": {nome: EFEITOS[nome] for nome in efeitos},
        "regras": [{"quando": "$sempre", "entao": list(efeitos), "para": "todos"}]}))


class RecusaDoJogo(Recusa):
    def __init__(self, dados: Any) -> None:
        super().__init__("mais fraco que o pedido vivo no canal", -32011)
        self.dados = dados


class PortaComALuzDoJogo(EscritasDeMentira):
    """A porta que só arbitra a luz: a do jogo, que não tem tópico, vence a mais fraca."""

    def __init__(self, luz_do_jogo: dict[str, float] | None = None, dados: Any = None,
                 **porta: bool) -> None:
        super().__init__(**porta)
        self.luz_do_jogo = luz_do_jogo or {}
        self.dados = dados
        self.recusas: list[tuple[float, str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "luz.set":
            forca = max(params["rgb"]) / 255 * params["brilho"]
            if forca <= self.luz_do_jogo.get(params["uniq"], 0.0):
                self.recusas.append((self.agora, metodo, dict(params)))
                raise RecusaDoJogo(self.dados)
        return await super().pedir(metodo, params)


def _motor(receita: Any, controles: list[dict[str, Any]] | None = None) -> Motor:
    motor = Motor(receita)
    motor.controles(controles if controles is not None else [{"uniq": UM, "jogador": 1}])
    return motor


def _correr(motor: Motor, porta: EscritasDeMentira, ate_ms: float,
            eventos: Sequence[tuple[float, Evento]] = (), de_ms: float = 0.0) -> Saida:
    fila = sorted(eventos, key=lambda e: e[0])
    saida = Saida(porta.pedir, None, motor.recusado, motor.pelo_motor)

    async def correr() -> None:
        k = round(de_ms / TIQUE)
        while (t := k * TIQUE) <= ate_ms:
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            await saida.aplicar(t, motor.passo(t))
            k += 1

    asyncio.run(correr())
    return saida


def rumble(uniq: str, forte: int, de_ms: float, ate_ms: float) -> list[tuple[float, Evento]]:
    batidas = [(t, ("jogo.vibracao", "jogo.vibracao", uniq, vibracao(uniq, forte, forte)))
               for t in range(int(de_ms), int(ate_ms), BATIDA_MS)]
    return [*batidas, (ate_ms, ("jogo.vibracao", "jogo.vibracao", uniq, vibracao(uniq, 0)))]


def haptica(uniq: str, nivel: float, de_ms: float, ate_ms: float) -> list[tuple[float, Evento]]:
    def evento(valor: float) -> Evento:
        return ("jogo.haptica", "jogo.haptica", uniq,
                {"uniq": uniq, "jogador": 1, "intensidade": [valor, valor], "t": 0.0})
    return [*[(t, evento(nivel)) for t in range(int(de_ms), int(ate_ms), BATIDA_MS)],
            (ate_ms, evento(0.0))]


def gatilho(uniq: str, lado: str, modo: str, forca: float, t_ms: float) -> tuple[float, Evento]:
    return (t_ms, ("jogo.gatilho", "jogo.gatilho", uniq, {
        "uniq": uniq, "jogador": 1, "lado": lado, "modo": modo, "forca": forca,
        "posicao": 0.2, "t": 0.0}))


def identidade(mascara: str) -> tuple[float, Evento]:
    return (0.0, ("jogo.identidade", "jogo.identidade", None, {
        "chave": "steam:1", "executavel": "jogo.exe", "loja": "steam", "mascara": mascara}))


def _motores(porta: EscritasDeMentira, uniq: str = UM) -> list[tuple[float, int]]:
    return [(round(t), p["forte"]) for t, p in porta.de("vibracao.set") if p["uniq"] == uniq]


def _lados(porta: EscritasDeMentira, metodo: str, uniq: str = UM) -> set[str]:
    return {p.get("lado", "-") for _, p in porta.de(metodo) if p["uniq"] == uniq}


def test_so_os_motores_o_jogo_ocupa_o_motor_e_a_receita_so_entra_quando_passa_dele() -> None:
    motor = _motor(_receita("motor", "luz", "gatilho", "coracao"))  # (noqa-acento)
    porta = PortaComALuzDoJogo(com_haptica=True)
    _correr(motor, porta, 2400, [*rumble(UM, 200, 0, 1000), *rumble(UM, 51, 1000, 2000)])
    assert motor.caminho.ocupadas(UM, 900) == {"motor"}
    assert _motores(porta) == [(1000, 128)]
    assert [t for t, _ in porta.de("luz.set")] == [0]
    assert _lados(porta, "gatilho.set") == {"esquerdo", "direito"}
    assert _lados(porta, "haptica.tocar") == {"esquerdo", "direito"}
    assert not porta.recusas


def test_motores_luz_e_gatilho_a_vaga_ocupada_muda_e_a_luz_se_aprende_pela_recusa() -> None:
    motor = _motor(_receita("motor", "luz", "gatilho", "coracao"))  # (noqa-acento)
    porta = PortaComALuzDoJogo({UM: 0.8}, com_haptica=True)
    _correr(motor, porta, 2000, [*rumble(UM, 51, 0, 2000),
                                 gatilho(UM, "direito", "resistencia", 0.9, 0)])  # (noqa-acento)
    assert motor.caminho.ocupadas(UM, 1900) == {"motor", "luz", "gatilho"}
    assert _motores(porta)[0] == (0, 128)
    assert [p["lado"] for _, p in porta.de("gatilho.set") if p["modo"] != "Off"] == ["esquerdo"]
    assert [t for t, _, _ in porta.recusas] == [0]
    assert porta.de("luz.set") == []
    assert (UM, "luz", "-") not in motor.vencedores


def test_a_haptica_do_jogo_ocupa_a_haptica_e_o_motor_sai_inteiro() -> None:
    motor = _motor(_receita("motor", "coracao"))  # (noqa-acento)
    porta = PortaComALuzDoJogo(com_haptica=True)
    _correr(motor, porta, 1500, haptica(UM, 0.9, 0, 1000))
    assert motor.caminho.ocupadas(UM, 900) == {"haptica"}
    assert _motores(porta)[0] == (0, 128)
    tocadas = [(round(t), p["lado"], p["forca"]) for t, p in porta.de("haptica.tocar")]  # (noqa-acento)
    assert tocadas == [(1000, "direito", 0.5), (1000, "esquerdo", 0.5)]


def test_sem_haptica_na_porta_o_coracao_disputa_com_o_motor_do_jogo() -> None:
    motor = _motor(_receita("coracao"))  # (noqa-acento)
    porta = PortaComALuzDoJogo()
    _correr(motor, porta, 1500, rumble(UM, 230, 0, 1000))
    assert motor.haptica_pelo_motor
    assert all(t >= 1000 for t, _ in _motores(porta))
    assert _motores(porta)


@pytest.mark.parametrize("mascara", ["xbox", "nintendo"])
def test_pela_mascara_sem_hidraw_a_luz_e_o_gatilho_saem_inteiros_e_a_recusa_nao_e_do_jogo(
        mascara: str) -> None:
    motor = _motor(_receita("luz", "gatilho"))
    porta = PortaComALuzDoJogo({UM: 0.8})
    _correr(motor, porta, 1000, [identidade(mascara)])
    assert _lados(porta, "gatilho.set") == {"esquerdo", "direito"}
    assert [t for t, _, _ in porta.recusas] == [0]
    assert motor.caminho.ocupadas(UM, 900) == set()
    assert (UM, "luz", "-") in motor.vencedores


def test_pela_mascara_dualsense_a_recusa_da_luz_ocupa_a_luz_pela_janela() -> None:
    motor = _motor(_receita("luz"))
    porta = PortaComALuzDoJogo({UM: 0.8})
    _correr(motor, porta, JANELA_MS - 100, [identidade("dualsense")])
    assert motor.caminho.ocupadas(UM, JANELA_MS - 100) == {"luz"}
    assert (UM, "luz", "-") not in motor.vencedores
    porta.luz_do_jogo.clear()
    _correr(motor, porta, JANELA_MS + 200, de_ms=JANELA_MS)
    [(t, _)] = porta.de("luz.set")
    assert JANELA_MS < t <= JANELA_MS + TIQUE + 1e-6


def test_a_recusa_de_outra_extensao_nao_e_o_caminho_do_jogo_e_nao_se_repete() -> None:
    motor = _motor(_receita("luz"))
    porta = PortaComALuzDoJogo({UM: 0.8}, dados={"vence": "extensao:outra"})  # (noqa-acento)
    _correr(motor, porta, 2000)
    assert motor.caminho.ocupadas(UM, 1900) == set()
    assert (UM, "luz", "-") in motor.vencedores
    assert len(porta.recusas) == 1


@pytest.mark.parametrize("mascara", ["dualsense", "xbox"])
def test_de_p1_a_p4_cada_controle_tem_o_proprio_caminho(mascara: str) -> None:
    motor = _motor(_receita("motor"), QUATRO_CONTROLES)
    porta = PortaComALuzDoJogo()
    _correr(motor, porta, 1500, [identidade(mascara), *rumble(DOIS, 200, 0, 1000),
                                 *rumble(QUATRO, 200, 0, 1000)])
    assert _motores(porta, UM) == [(0, 128)]
    assert _motores(porta, TRES) == [(0, 128)]
    assert _motores(porta, DOIS) == [(1000, 128)]
    assert _motores(porta, QUATRO) == [(1000, 128)]
    assert [motor.caminho.ocupadas(u, 900) for u in (UM, DOIS, TRES, QUATRO)] == [
        set(), {"motor"}, set(), {"motor"}]


def test_o_rumble_sem_batida_vale_zero_e_o_jogo_que_fecha_solta_tudo() -> None:
    motor = _motor(_receita("motor", "gatilho"))
    porta = PortaComALuzDoJogo()
    sem_zero = [(0.0, ("jogo.vibracao", "jogo.vibracao", UM, vibracao(UM, 200, 200)))]
    fechou = (1500.0, ("jogo.vibracao", "jogo.fechou", None, {"appid": 1}))
    _correr(motor, porta, 2000, [*sem_zero, gatilho(UM, "direito", "resistencia", 0.9, 0),  # (noqa-acento)
                                 fechou])
    primeiro = _motores(porta)[0][0]
    assert SEM_BATIDA_MS < primeiro <= SEM_BATIDA_MS + 2 * TIQUE
    assert [round(t) for t, p in porta.de("gatilho.set") if p["lado"] == "direito"] == [1500]


def test_o_gatilho_do_jogo_segura_a_vaga_ate_mudar_mesmo_depois_da_janela() -> None:
    motor = _motor(_receita("gatilho"))
    porta = PortaComALuzDoJogo()
    fim = 2 * JANELA_MS
    troca = fim - 500
    _correr(motor, porta, fim, [gatilho(UM, "direito", "resistencia", 0.9, 0),  # (noqa-acento)
                                gatilho(UM, "direito", "desligado", 0.0, troca)])
    direito = [round(t) for t, p in porta.de("gatilho.set") if p["lado"] == "direito"]
    assert motor.caminho.ocupadas(UM, troca - TIQUE) == {"gatilho"}
    assert direito and troca <= direito[0] <= troca + 2 * TIQUE


def test_o_servidor_assina_o_que_o_jogo_escreve_nos_canais_da_receita() -> None:
    assert servidor.topicos_do_caminho(_receita("luz")) == {"jogo.identidade"}
    assert servidor.topicos_do_caminho(_receita("motor")) == {"jogo.vibracao", "jogo.identidade"}
    assert servidor.topicos_do_caminho(_receita("coracao")) == {  # (noqa-acento)
        "jogo.vibracao", "jogo.haptica", "jogo.identidade"}
    assert servidor.topicos_da_receita(_receita("gatilho", "luz")) == [  # (noqa-acento)
        "conexao", "jogo.gatilho", "jogo.identidade"]  # (noqa-acento)
    assert "caminho" not in json.dumps(_receita("motor").dados)


def test_a_recusa_da_porta_leva_o_data_ate_o_caminho() -> None:
    motor = _motor(_receita("luz"), QUATRO_CONTROLES[:2])
    quem_vence = {UM: "jogo", DOIS: "extensao:outra"}  # (noqa-acento)

    async def corpo() -> None:
        leitor = asyncio.StreamReader()

        class Escritor:
            def write(self, linha: bytes) -> None:
                pedido = json.loads(linha)
                leitor.feed_data(json.dumps({"jsonrpc": "2.0", "id": pedido["id"], "error": {
                    "code": -32011, "message": "mais fraco que o pedido vivo no canal",
                    "data": {"vence": quem_vence[pedido["params"]["uniq"]]}}}).encode() + b"\n")

            async def drain(self) -> None:
                return None

            def close(self) -> None:
                return None

        porta = servidor.Porta(leitor, cast(asyncio.StreamWriter, Escritor()))
        saida = Saida(porta.pedir, None, motor.recusado)
        await saida.aplicar(0.0, motor.passo(0.0))
        porta.fechar()

    asyncio.run(corpo())
    assert motor.caminho.ocupadas(UM, 10) == {"luz"}
    assert motor.caminho.ocupadas(DOIS, 10) == set()
