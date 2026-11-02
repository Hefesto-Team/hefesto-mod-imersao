"""O peso da mira pela receita: o perigo pede ``mira.peso`` ao Hefesto pelo caminho dos outros
pedidos, e o controle calado, a opção desligada, a Força em zero e a recusa do jogo o calam."""
from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

import pytest
from apoio import DOIS, RAIZ, UM, EscritasDeMentira, Recusa
from test_a_janela_do_modo_imersao import TENSO
from test_a_receita_minecraft_dungeons_ii import _batimento
from test_a_receita_minecraft_dungeons_ii import _motor as _dungeons
from test_o_universal import Evento, _universal

import opcoes as ajustes
from efeitos import peso_da_mira
from motor.laco import HZ, Motor
from motor.saida import Saida
from receita.formato import ReceitaRecusada, ler_receita

NAO_ESCREVEU = -32013
DOIS_CONTROLES = [{"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}]


class PortaDaMira(EscritasDeMentira):
    """A porta que recusa o ``mira.peso`` com o código de erro dado antes de ``recusa_ate``."""

    def __init__(self, codigo: int | None = None) -> None:
        super().__init__(com_haptica=True, com_som=True)
        self.codigo = codigo
        self.recusa_ate = float("inf")
        self.recusadas: list[tuple[float, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "mira.peso" and self.codigo is not None and self.agora < self.recusa_ate:
            self.recusadas.append((self.agora, dict(params)))
            raise Recusa("este jogo usa um anticheat: o peso da mira pede a chave", self.codigo)
        return await super().pedir(metodo, params)


def _jogo(chave: str) -> Evento:
    return ("perfil.jogo", "perfil.jogo", None, {"jogo": chave, "memoria": False})


def _correr(motor: Motor, porta: EscritasDeMentira, ate_ms: float,
            eventos: list[tuple[float, Evento]]) -> list[str]:
    fila = sorted(eventos, key=lambda e: e[0])
    diario: list[str] = []
    saida = Saida(porta.pedir, diario.append, motor.recusado, motor.pelo_motor)

    async def correr() -> None:
        k = 0
        while (t := k * 1000 / HZ) <= ate_ms:
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            await saida.aplicar(t, motor.passo(t))
            k += 1

    asyncio.run(correr())
    return diario


def _pesos(porta: EscritasDeMentira, uniq: str = UM) -> list[tuple[float, dict[str, Any]]]:
    return [(t, p) for t, p in porta.de("mira.peso") if p["uniq"] == uniq]


def test_o_perigo_do_universal_pesa_a_mira_pela_receita_e_renova_antes_do_prazo() -> None:
    porta = PortaDaMira()
    _correr(_universal(None, {}), porta, 20_000, TENSO)
    pesos = _pesos(porta)
    assert pesos
    assert all(0.6 <= p["ganho"] < 1.0 for _, p in pesos)
    assert {p["ate_ms"] for _, p in pesos} == {peso_da_mira.PRAZO_MS}
    instantes = [t for t, _ in pesos]
    assert max(b - a for a, b in itertools.pairwise(instantes)) < peso_da_mira.PRAZO_MS


def test_sem_perigo_nada_se_pede_e_o_alivio_deixa_o_prazo_devolver_a_mira() -> None:
    sem_perigo = PortaDaMira()
    _correr(_universal(None, {}), sem_perigo, 5000, [])
    assert sem_perigo.de("mira.peso") == []

    motor = _dungeons({})
    porta = PortaDaMira()
    fila = sorted(_batimento(0, 9000), key=lambda e: e[0])
    pesando: list[tuple[float, bool]] = []

    async def correr() -> None:
        saida = Saida(porta.pedir, None, motor.recusado, motor.pelo_motor)
        k = 0
        while (t := k * 1000 / HZ) <= 30_000:
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            vencedores = motor.passo(t)
            pesando.append((t, any(c == "mira" for _, c, _ in vencedores)))
            await saida.aplicar(t, vencedores)
            k += 1

    asyncio.run(correr())
    solto = next(t for (_, antes), (t, agora) in itertools.pairwise(pesando) if antes and not agora)
    pesos = _pesos(porta)
    assert pesos and {p["ganho"] for _, p in pesos} >= {0.6, 0.9}
    assert all(0.6 <= p["ganho"] < 1.0 for _, p in pesos)
    assert not any(agora for t, agora in pesando if t >= solto)
    assert [t for t, _ in pesos if t >= solto] == []
    assert solto - pesos[-1][0] <= peso_da_mira.RENOVA_MS


def test_o_controle_calado_nao_recebe_o_peso_e_o_outro_segue() -> None:
    motor = _universal(DOIS_CONTROLES, {})
    motor.calar({DOIS})
    porta = PortaDaMira()
    _correr(motor, porta, 20_000, TENSO)
    assert _pesos(porta, UM)
    assert _pesos(porta, DOIS) == []


def test_a_opcao_desligada_e_a_forca_em_zero_nao_pedem_nada_e_a_metade_pesa_a_metade() -> None:
    for opcoes in ({peso_da_mira.OPCAO: False}, {ajustes.FORCA: 0}):
        porta = PortaDaMira()
        _correr(_universal(None, opcoes), porta, 20_000, TENSO)
        assert porta.de("mira.peso") == []
    cheia, metade = PortaDaMira(), PortaDaMira()
    _correr(_universal(None, {}), cheia, 20_000, TENSO)
    _correr(_universal(None, {ajustes.FORCA: 50}), metade, 20_000, TENSO)
    peso_cheio = 1 - min(p["ganho"] for _, p in _pesos(cheia))
    peso_metade = 1 - min(p["ganho"] for _, p in _pesos(metade))
    assert peso_metade == pytest.approx(peso_cheio / 2, abs=peso_da_mira.DEGRAU)


def test_a_opcao_peso_da_mira_nasce_ligada_e_o_manifesto_pede_escrever_mira() -> None:
    manifesto = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    opcao = next(o for o in manifesto["opcoes"] if o["id"] == peso_da_mira.OPCAO)  # (noqa-acento)
    assert (opcao["grupo"], opcao["tipo"], opcao["padrao"]) == ("Efeitos", "ligado", True)  # (noqa-acento)
    assert peso_da_mira.PADRAO is True
    assert "escrever:mira" in manifesto["permissoes"]  # (noqa-acento)


@pytest.mark.parametrize("arquivo", ["universal.json", "estudadas/minecraft-dungeons-ii.json"])
def test_as_receitas_de_fabrica_pesam_a_mira_de_1_a_0_6(arquivo: str) -> None:
    receita = ler_receita((RAIZ / "receitas" / arquivo).read_bytes())
    miras = [e for e in receita.secao("efeitos").values() if e["canal"] == "mira"]
    assert len(miras) == 1
    motor = Motor(receita, {})
    caminho = next(c for c in receita.expressoes if c[-1] == "ganho")
    for perigo, esperado in ((0.0, 1.0), (1.0, 0.6)):
        motor.valores["tensao"] = perigo  # (noqa-acento)
        assert motor._avaliar(caminho) == pytest.approx(esperado)


def test_a_recusa_do_jogo_cala_a_mira_sem_repetir_e_o_jogo_novo_a_devolve() -> None:
    porta = PortaDaMira(NAO_ESCREVEU)
    porta.recusa_ate = 4000.0
    linha = [(0, _jogo("steam_app_1")), (3000, _jogo("steam_app_1")),
             (5000, _jogo("steam_app_2")), *_batimento(0, 9000)]
    diario = _correr(_dungeons({}), porta, 9000, linha)
    assert len(porta.recusadas) == 1
    assert porta.de("haptica.tocar")
    assert not [f for f in diario if "mira" in f]
    aceitos = [t for t, _ in porta.de("mira.peso")]
    assert aceitos and 5000 <= min(aceitos) < 5000 + peso_da_mira.RENOVA_MS


def test_a_porta_sem_o_mira_peso_cala_o_canal_uma_vez_so() -> None:
    porta = PortaDaMira(-32601)
    diario = _correr(_universal(None, {}), porta, 20_000, TENSO)
    assert len(porta.recusadas) == 1
    assert len([f for f in diario if "mira" in f]) == 1


@pytest.mark.parametrize("ganho", [0.29, 1.01])
def test_a_receita_recusa_o_ganho_fora_de_0_3_a_1(ganho: float) -> None:
    efeito: dict[str, Any] = {"canal": "mira", "ganho": ganho}
    dados = {"formato": 1, "motor": ">=1,<2", "permissoes": ["ler:jogo.som"],  # (noqa-acento)
             "sentidos": {"estalo": {"de": "jogo.som", "especie": "evento", "nome": "jogo.som"}},
             "efeitos": {"pesa": efeito},
             "regras": [{"quando": "estalo", "entao": "pesa", "para": "todos"}]}
    with pytest.raises(ReceitaRecusada):
        ler_receita(json.dumps(dados))
    efeito["ganho"] = 0.6
    assert ler_receita(json.dumps(dados)).secao("efeitos")["pesa"]["canal"] == "mira"


def test_a_recusa_que_dura_pede_de_novo_so_de_tempos_em_tempos_e_a_chave_ligada_no_jogo_volta(
) -> None:
    porta = PortaDaMira(NAO_ESCREVEU)
    porta.recusa_ate = 9000.0
    linha = [(0, _jogo("steam_app_1")), *_batimento(0, 15_000)]
    diario = _correr(_dungeons({}), porta, 15_000, linha)
    instantes = [t for t, _ in porta.recusadas]
    assert len(instantes) >= 2
    assert min(b - a for a, b in itertools.pairwise(instantes)) >= peso_da_mira.TENTA_DE_NOVO_MS
    aceitos = [t for t, _ in porta.de("mira.peso")]
    assert aceitos and min(aceitos) - 9000.0 <= peso_da_mira.TENTA_DE_NOVO_MS
    assert not [f for f in diario if "mira" in f]


def test_o_peso_que_a_forca_arredonda_a_zero_nao_se_pede() -> None:
    assert peso_da_mira.ganho(0.6, 0.05) == 1.0
    porta = PortaDaMira()
    _correr(_universal(None, {ajustes.FORCA: 5}), porta, 20_000, TENSO)
    assert porta.de("haptica.tocar")
    assert porta.de("mira.peso") == []
