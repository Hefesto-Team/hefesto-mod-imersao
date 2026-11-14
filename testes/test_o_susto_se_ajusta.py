"""O susto se ajusta na janela (duração, volume e força, em toda receita) e a tela só se lê no
clique «Ver a tela», contra uma porta de mentira com o contrato do ``tela.ver``/``tela.parar`` e o
``dura_s`` do recorte; o Hefesto que não conhece o pedido vira a linha «Tela», nunca erro em laço."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, QUATRO_CONTROLES, TRES, UM, EscritasDeMentira, Recusa
from test_o_universal import _correr, _universal, microfone, na_mao, som

import opcoes as ajustes
import servidor
from motor import efeitos as catalogo

SUSTO_EM_MS = 18_000
TIQUE_MS = 1000 / 60


def _linha(uniq: str = UM) -> list[Any]:
    return ([(t, microfone(uniq, 0.01)) for t in range(0, 20_000, 500)] + na_mao(uniq, 20_000)
            + [(SUSTO_EM_MS, som("direito", 0.45, 1234.5))])


LINHA = _linha()
AJUSTADO = {"duracao_do_susto": 600, "volume_do_susto": 40, "forca_do_susto": 50}
SEM_PONTE = -32015
MESAS: dict[str, list[dict[str, Any]]] = {
    "um": [{"uniq": UM, "jogador": 1}],
    "so-o-p3": [{"uniq": TRES, "jogador": 3}],
    "buraco-no-meio": [{"uniq": UM, "jogador": 1}, {"uniq": TRES, "jogador": 3}],
    "quatro": QUATRO_CONTROLES,
}


class PortaQueGuardaOsRegistros(EscritasDeMentira):
    """A porta de mentira que guarda os golpes de cada ``haptica.registrar`` e recusa o
    ``som.tocar`` com ``-32015`` nos controles pelo rádio sem vaga na ponte."""

    def __init__(self, sem_ponte: frozenset[str] = frozenset(), **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.golpes: dict[str, list[list[float]]] = {}
        self.sem_ponte = sem_ponte

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "haptica.registrar" and self.com_haptica:
            self.golpes[params["id"]] = params["golpes"]
        if metodo == "som.tocar" and params["uniq"] in self.sem_ponte:
            raise Recusa("som.tocar: o rádio sem vaga na ponte", SEM_PONTE)
        return await super().pedir(metodo, params)


def _sustos(porta: EscritasDeMentira, uniq: str) -> list[tuple[float, dict[str, Any]]]:
    return [(t, p) for t, p in porta.de("haptica.tocar")
            if p["id"] == "susto" and p["uniq"] == uniq]  # (noqa-acento)


def _quanto_durou(porta: EscritasDeMentira, uniq: str) -> float:
    """Do primeiro toque do susto até a escrita seguinte do mesmo lado que já não é ele."""
    tocados = [(t, p) for t, p in porta.de("haptica.tocar")
               if p["uniq"] == uniq and p["lado"] == "esquerdo"]
    inicio = next(t for t, p in tocados if p["id"] == "susto" and p["forca"] > 0)  # (noqa-acento)
    fim = next(t for t, p in tocados if t > inicio and (p["id"] != "susto" or not p["forca"]))  # (noqa-acento)
    return fim - inicio


def test_a_duracao_escala_os_golpes_do_susto_com_a_mesma_forma() -> None:
    base = catalogo.PADROES["susto"]
    longo = catalogo.padrao("susto", 600)
    assert longo.dura_ms == 600 and base.dura_ms == 300
    for antes, depois in zip(base.golpes, longo.golpes, strict=True):
        assert (depois.inicio_ms, depois.dura_ms) == (antes.inicio_ms * 2, antes.dura_ms * 2)
        assert (depois.frequencia_hz, depois.amplitude) == (antes.frequencia_hz, antes.amplitude)
    assert catalogo.padrao("susto", 300) is base and catalogo.padrao("susto") is base
    assert catalogo.padrao("coracao", 900) is catalogo.PADROES["coracao"]  # (noqa-acento)
    assert catalogo.envelope("susto", 590, dura_ms=600) > 0 == catalogo.envelope("susto", 590)


@pytest.mark.parametrize("mesa", sorted(MESAS))
def test_o_susto_chega_com_a_duracao_o_volume_e_a_forca_da_janela_em_cada_controle(
        mesa: str) -> None:
    controles = MESAS[mesa]
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    _correr(_universal(controles, AJUSTADO), porta, 19_000, _linha(controles[0]["uniq"]))
    uniqs = sorted(c["uniq"] for c in controles)
    assert sorted(p["uniq"] for _, p in porta.de("som.tocar")) == uniqs
    for _, pedido in porta.de("som.tocar"):
        assert (pedido["volume"], pedido["dura_s"], pedido["t"]) == (0.4, 0.6, 1234.5)
    assert porta.golpes["susto"] == catalogo.golpes(catalogo.padrao("susto", 600))
    for uniq in uniqs:
        assert {p["forca"] for _, p in _sustos(porta, uniq) if p["forca"]} == {0.5}
        assert 600 <= _quanto_durou(porta, uniq) <= 600 + 2 * TIQUE_MS


def test_a_receita_no_padrao_toca_o_susto_de_antes() -> None:
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    _correr(_universal(), porta, 19_000, LINHA)
    assert [(p["volume"], p["dura_s"]) for _, p in porta.de("som.tocar")] == [(1.0, 0.3)]
    assert {p["forca"] for _, p in _sustos(porta, UM) if p["forca"]} == {1.0}
    assert porta.golpes["susto"] == catalogo.golpes(catalogo.PADROES["susto"])
    assert 300 <= _quanto_durou(porta, UM) <= 300 + 2 * TIQUE_MS


def test_sem_a_haptica_na_porta_o_motor_imita_o_susto_pela_duracao_nova() -> None:
    porta = EscritasDeMentira(com_som=True)
    _correr(_universal(opcoes={**AJUSTADO, "forca_do_susto": 100}), porta, 19_000, LINHA)
    motores = [(t, p["forte"]) for t, p in porta.de("vibracao.set") if t >= SUSTO_EM_MS]
    ligado = next(t for t, f in motores if f)
    desligado = next(t for t, f in motores if t > ligado and not f)
    assert desligado - ligado >= 560


def test_volume_e_forca_em_zero_calam_o_susto_e_o_resto_segue() -> None:
    porta = PortaQueGuardaOsRegistros(com_haptica=True, com_som=True)
    _correr(_universal(opcoes={"volume_do_susto": 0, "forca_do_susto": 0}), porta, 19_000, LINHA)
    assert not porta.de("som.tocar") and not _sustos(porta, UM)
    assert any(p["id"] == "coracao" for _, p in porta.de("haptica.tocar"))  # (noqa-acento)


def test_mesa_mista_o_radio_sem_ponte_recusa_o_som_e_os_outros_tocam() -> None:
    porta = PortaQueGuardaOsRegistros(frozenset({DOIS, QUATRO}), com_haptica=True, com_som=True)
    saida, diario = _correr(_universal(QUATRO_CONTROLES, AJUSTADO), porta, 19_000, LINHA)
    assert sorted(p["uniq"] for _, p in porta.de("som.tocar")) == [UM, TRES]
    for uniq in (UM, DOIS, TRES, QUATRO):
        assert {p["forca"] for _, p in _sustos(porta, uniq) if p["forca"]} == {0.5}
    assert not saida.sem_som
    assert sum("som.tocar recusado" in frase for frase in diario) == 2


def test_a_receita_aceita_a_expressao_no_volume_na_forca_e_na_duracao() -> None:
    receita = servidor.carregar_o_universal()
    efeitos = receita.secao("efeitos")
    assert efeitos["susto_no_alto_falante"]["volume"] == "$volume_do_susto / 100"
    assert efeitos["susto_no_alto_falante"]["dura_ms"] == "$duracao_do_susto"
    assert efeitos["susto_no_tato"]["forca"] == "$forca_do_susto / 100"
    assert efeitos["susto_no_tato"]["dura_ms"] == "$duracao_do_susto"


class PortaDaTela:
    """A porta com o contrato da A-TELA-SO-SE-LE-NO-CLIQUE-01, ou o Hefesto de antes dele."""

    def __init__(self, conhece: bool = True) -> None:
        self.conhece = conhece
        self.pedidos: list[tuple[str, dict[str, Any]]] = []
        self.assinados: set[str] = set()

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        if metodo in ("tela.ver", "tela.parar") and not self.conhece:
            raise servidor.RecusaDaPorta(f"método desconhecido: {metodo}", -32601)
        if metodo == "eventos.assinar":
            self.assinados |= set(params["topicos"])
        elif metodo == "eventos.desassinar":
            self.assinados -= set(params["topicos"])
        elif metodo == "controles.lista":
            return {"controles": QUATRO_CONTROLES}
        return {"status": "ok"}

    def conta(self, metodo: str) -> int:
        return sum(1 for m, _ in self.pedidos if m == metodo)

    def assinou_a_tela(self) -> int:
        return sum(1 for m, p in self.pedidos
                   if m == "eventos.assinar" and "jogo.tela" in p["topicos"])


def _acao(acao: str) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": "extensao.acao", "nome": "extensao.acao",
                                           "uniq": None, "dados": {"mod": "imersao", "acao": acao,
                                                                   "alvo": None}}}


def _jogo(jogo: str | None) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": "perfil.jogo", "nome": "perfil.trocou",
                                           "uniq": None, "dados": {"jogo": jogo}}}


def _linha_da_tela(extensao: servidor.Extensao) -> str | None:
    return next((linha["valor"] for linha in extensao.linhas() if linha["rotulo"] == "Tela"),
                None)


def _extensao(porta: PortaDaTela, dados: Path) -> servidor.Extensao:
    return servidor.Extensao(porta, servidor.carregar_o_universal(), None, dados)  # type: ignore[arg-type]


def test_sem_o_clique_nada_assina_a_tela_e_com_ele_um_ate_o_segundo_clique(tmp_path: Path) -> None:
    porta = PortaDaTela()

    async def corpo() -> None:
        extensao = _extensao(porta, tmp_path)
        await extensao.atualizar_os_controles()
        await extensao.assinar()
        assert porta.conta("tela.ver") == 0 and "jogo.tela" not in porta.assinados
        await extensao.ao_evento(_acao(ajustes.ACAO_DE_VER_A_TELA))
        assert porta.conta("tela.ver") == 1 and porta.assinou_a_tela() == 1
        assert extensao.motor.opcoes[ajustes.SENTIDO_DA_TELA] is True
        assert _linha_da_tela(extensao) == servidor.TELA_VENDO
        assert "tela" in extensao.sentidos_lendo()
        await extensao.ao_evento(_acao(ajustes.ACAO_DE_VER_A_TELA))
        assert porta.conta("tela.parar") == 1 and "jogo.tela" not in porta.assinados
        assert extensao.motor.opcoes[ajustes.SENTIDO_DA_TELA] is False
        assert _linha_da_tela(extensao) is None
        await extensao.ao_evento(_acao(ajustes.ACAO_DE_PARAR_DE_VER))
        assert porta.conta("tela.parar") == 1

    asyncio.run(corpo())
    assert porta.conta("tela.ver") == 1 and porta.assinou_a_tela() == 1
    assert not (tmp_path / "opcoes.json").exists()


def test_o_jogo_que_fecha_para_de_ver_a_tela(tmp_path: Path) -> None:
    porta = PortaDaTela()

    async def corpo() -> None:
        extensao = _extensao(porta, tmp_path)
        await extensao.ao_evento(_jogo("steam_app_1"))
        await extensao.ao_evento(_acao(ajustes.ACAO_DE_VER_A_TELA))
        assert "jogo.tela" in porta.assinados
        await extensao.ao_evento(_jogo(None))
        assert "jogo.tela" not in porta.assinados and porta.conta("tela.parar") == 1
        assert not extensao.vendo

    asyncio.run(corpo())


def test_o_hefesto_sem_tela_ver_vira_a_linha_da_tela_e_nunca_assina_nem_repete(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaDaTela(conhece=False)

    async def corpo() -> None:
        extensao = _extensao(porta, tmp_path)
        for _ in range(3):
            await extensao.ao_evento(_acao(ajustes.ACAO_DE_VER_A_TELA))
        assert _linha_da_tela(extensao) == servidor.TELA_SEM_O_PEDIDO
        assert not extensao.vendo and extensao.motor.opcoes[ajustes.SENTIDO_DA_TELA] is False
        await asyncio.sleep(0.2)
        await extensao.ao_evento(_acao(ajustes.ACAO_DE_PARAR_DE_VER))
        assert _linha_da_tela(extensao) is None

    asyncio.run(corpo())
    assert porta.conta("tela.ver") == 3
    assert porta.assinou_a_tela() == 0 and porta.conta("tela.parar") == 0
    assert capsys.readouterr().err.count("tela.ver recusado") == 1


def test_o_opcoes_json_com_a_tela_ligada_migra_para_desligada(tmp_path: Path) -> None:
    (tmp_path / "opcoes.json").write_text(json.dumps({"sentido_tela": True, "forca_geral": 70}),
                                          encoding="utf-8")
    porta = PortaDaTela()
    extensao = _extensao(porta, tmp_path)
    assert extensao.opcoes[ajustes.SENTIDO_DA_TELA] is False
    asyncio.run(extensao.assinar())
    assert "jogo.tela" not in porta.assinados
    assert ajustes.migrar(tmp_path) is True
    assert json.loads((tmp_path / "opcoes.json").read_text(encoding="utf-8")) == {
        "forca_geral": 70}
    assert ajustes.migrar(tmp_path) is False
    assert ajustes.consentir(tmp_path, "jogo.tela") is False


def test_o_tela_ver_e_um_so_para_a_mesa_inteira(tmp_path: Path) -> None:
    porta = PortaDaTela()

    async def corpo() -> None:
        extensao = _extensao(porta, tmp_path)
        await extensao.atualizar_os_controles()
        await extensao.ao_evento(_acao(ajustes.ACAO_DE_VER_A_TELA))
        assert len(extensao.controles) == 4

    asyncio.run(corpo())
    assert porta.conta("tela.ver") == 1
    assert all(p == {} for m, p in porta.pedidos if m in ("tela.ver", "tela.parar"))
