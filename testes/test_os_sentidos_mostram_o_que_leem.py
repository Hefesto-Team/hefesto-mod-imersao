"""A janela do Modo imersão sem a coluna «Agora»: a faixa do alto e o que cada sentido lê.

A extensão publica, no ``acessorios.estado``, a ``situacao`` (esperando um jogo, tocando com o nome
do jogo, ou calado com o motivo) e as ``leituras`` de cada sentido, de 0 a 100, que a janela
desenha ao lado da chave dele. A escolha da «Receita» de antes vira a do «Ajuste» de mesmo
sentido, e o «O golpe vai para» sai do arquivo.

MORDIDAS: tirar a frase do calado em ``Extensao.situacao`` reprova o motivo da recusa; ler o
medidor sem a meia-vida reprova a queda; tirar a troca do ``migrar`` devolve a escolha dela ao
padrão.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, UM
from test_o_universal import entradas, microfone, rumble, som

import opcoes as ajustes
import servidor

NATIVO = "no Modo Nativo o jogo fala direto com o controle"
DOIS_CONTROLES = [{"uniq": UM, "jogador": 1, "cor": "Cosmic Red"},
                  {"uniq": DOIS, "jogador": 2, "cor": "Starlight Blue"}]


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"controles": DOIS_CONTROLES} if metodo == "controles.lista" else {}


class _Relogio:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _evento(evento: tuple[str, str, str | None, dict[str, Any]]) -> dict[str, Any]:
    topico, nome, uniq, dados = evento
    return {"method": "evento", "params": {"topico": topico, "nome": nome, "uniq": uniq,
                                           "dados": dados}}


def _jogo(perfil: str | None = "Sackboy", em_cena: bool = True) -> dict[str, Any]:
    return _evento(("perfil.jogo", "perfil.trocou", None, {
        "perfil": perfil, "jogo": "steam_app_1599660" if em_cena else None, "em_cena": em_cena,
        "estilo": None, "controles": [], "memoria": False, "t": 1.0}))


def _extensao(*eventos: dict[str, Any]) -> tuple[servidor.Extensao, _Relogio]:
    extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal())  # type: ignore[arg-type]
    relogio = _Relogio()
    extensao.relogio = relogio

    async def corpo() -> None:
        await extensao.assinar()
        await extensao.atualizar_os_controles()
        for evento in eventos:
            await extensao.ao_evento(evento)

    asyncio.run(corpo())
    return extensao, relogio


def _leitura(extensao: servidor.Extensao, opcao: str) -> dict[str, Any]:
    return next(x for x in extensao.leituras() if x["opcao"] == opcao)


def _aceito(estado: dict[str, Any]) -> dict[str, Any]:
    porta_do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.porta")
    aceito: dict[str, Any] = porta_do_hefesto.estado_dos_acessorios(
        "imersao", estado, acoes_dos_aparelhos=frozenset({"ligar"}))
    return aceito


def test_o_medidor_do_som_sobe_com_o_som_do_jogo_cai_com_o_tempo_e_zera_desligado() -> None:
    """Os sentidos mostram o que leem: o estalo de 0,8 põe o som em 80, a meia-vida o derruba, e
    o sentido desligado na janela fica em zero."""
    extensao, relogio = _extensao(_evento(som("esquerdo", 0.8, 0.2)),
                                  _evento(microfone(UM, 0.3)), _evento(rumble(DOIS, 255)),
                                  _evento(entradas(UM, 128)))
    assert _leitura(extensao, "sentido_som") == {"opcao": "sentido_som", "nivel": 80}
    assert _leitura(extensao, "sentido_microfone")["nivel"] == 30
    assert _leitura(extensao, "sentido_vibracao")["nivel"] == 100
    assert _leitura(extensao, "sentido_golpe")["nivel"] == 50
    assert "nivel" not in _leitura(extensao, "sentido_parado")
    relogio.t += servidor.MEIA_VIDA_DA_LEITURA_S
    assert _leitura(extensao, "sentido_som")["nivel"] == 40
    relogio.t += 10
    assert _leitura(extensao, "sentido_som")["nivel"] == 0
    asyncio.run(extensao.ao_evento(_evento(som("direito", 0.6, 0.3))))
    extensao.opcoes = {**extensao.opcoes, "sentido_som": False}
    assert _leitura(extensao, "sentido_som") == {"opcao": "sentido_som", "nivel": 0}
    assert _aceito(extensao._estado())["leituras"][0] == {
        "opcao": "sentido_som", "nivel": 0, "frase": None, "cego": False}


def test_o_microfone_mudo_le_zero() -> None:
    extensao, _ = _extensao(_evento(microfone(UM, 0.7, mudo=True)))
    assert _leitura(extensao, "sentido_microfone")["nivel"] == 0


def test_a_faixa_espera_um_jogo_e_toca_com_o_nome_do_jogo() -> None:
    """A faixa do alto: sem jogo em cena, esperando; com ele, tocando, com o nome do perfil."""
    extensao, _ = _extensao()
    assert extensao.situacao() == {"estado": "esperando", "frase": None}
    asyncio.run(extensao.ao_evento(_jogo()))
    assert extensao.situacao() == {"estado": "tocando", "frase": "Sackboy"}
    asyncio.run(extensao.ao_evento(_jogo(None, em_cena=False)))
    assert extensao.situacao() == {"estado": "esperando", "frase": None}
    assert _aceito(extensao._estado())["situacao"] == {"estado": "esperando", "frase": None}


def test_a_faixa_diz_o_motivo_do_calado() -> None:
    """Calado com o motivo: a intensidade em zero, nenhum controle que sente, ou a porta que
    recusa cada controle que sente, com a frase dela."""
    extensao, relogio = _extensao(_jogo())
    extensao.motor.opcoes[ajustes.FORCA] = 0
    assert extensao.situacao() == {"estado": "calado", "frase": servidor.CALADO_SEM_INTENSIDADE}
    extensao.motor.opcoes[ajustes.FORCA] = 100
    extensao.calados = frozenset({"jogador-1", "jogador-2"})
    assert extensao.situacao() == {"estado": "calado", "frase": servidor.CALADO_SEM_QUEM_SINTA}
    extensao.calados = frozenset()
    extensao.recusado_em = {UM: (NATIVO, relogio.t), DOIS: (NATIVO, relogio.t)}
    assert extensao.situacao() == {
        "estado": "calado", "frase": "No Modo Nativo o jogo fala direto com o controle"}
    assert _aceito(extensao._estado())["situacao"]["frase"].startswith("No Modo Nativo")


def test_so_um_controle_recusado_segue_tocando_e_a_linha_diz_quem_nao_recebe() -> None:
    extensao, relogio = _extensao(_jogo())
    extensao.recusado_em = {DOIS: (NATIVO, relogio.t)}
    assert extensao.situacao()["estado"] == "tocando"
    linhas = {x["rotulo"]: x["valor"] for x in extensao.linhas()}
    assert linhas["Sentem"] == "Cosmic Red, Starlight Blue"
    assert linhas["Não recebe"] == "Starlight Blue"
    extensao.tocou_em[DOIS] = relogio.t + 1
    assert "Não recebe" not in {x["rotulo"] for x in extensao.linhas()}
    relogio.t += servidor.RECUSA_RECENTE_S + 5
    extensao.recusado_em = {UM: (NATIVO, 0.0), DOIS: (NATIVO, 0.0)}
    assert extensao.situacao()["estado"] == "tocando"


def test_a_tensao_da_cena_em_palavras_so_no_terror() -> None:
    """A «Tensão da cena» em palavras, só no estilo Terror; o número de 0 a 10 não vai à tela."""
    assert [servidor.tensao_da_cena(c, 6) for c in (0, 2, 4, 6, 8, 9)] == [
        "Calma", "Calma", "Atenta", "Tensa", "Tensa", "Pânico"]
    extensao, _ = _extensao(_jogo())
    assert "Tensão da cena" not in {x["rotulo"] for x in extensao.linhas()}
    extensao.opcoes = {**extensao.opcoes, "estilo": "Terror"}
    extensao.aplicar_o_estilo()
    assert {x["rotulo"] for x in extensao.linhas()} >= {"Estilo", "Tensão da cena"}
    assert all(len(x["valor"]) <= servidor.TETO_DO_VALOR for x in extensao.linhas())


def test_a_escolha_de_antes_da_receita_vira_a_do_ajuste_e_o_golpe_para_quem_sai(
        tmp_path: Path) -> None:
    """O «Ajuste» (Automático, Sempre o universal) no lugar da «Receita»: a escolha de antes
    não se perde, e o «O golpe vai para» sai do arquivo."""
    arquivo = tmp_path / ajustes.ARQUIVO_DAS_OPCOES
    for antes, depois in (("Universal", ajustes.SEMPRE_O_UNIVERSAL),
                          ("Pelo jogo", ajustes.AUTOMATICO)):
        arquivo.write_text(json.dumps({"receita": antes, "para_quem": "Todos os controles",
                                       "forca_geral": 80}), encoding="utf-8")
        assert ajustes.migrar(tmp_path)
        assert json.loads(arquivo.read_text(encoding="utf-8")) == {"receita": depois,
                                                                    "forca_geral": 80}
        assert not ajustes.migrar(tmp_path)
    assert servidor.escolha_da_receita({"receita": ajustes.SEMPRE_O_UNIVERSAL}) == \
        servidor.UNIVERSAL_SEMPRE
    assert servidor.escolha_da_receita({"receita": "Universal"}) == servidor.UNIVERSAL_SEMPRE
    assert servidor.escolha_da_receita({"receita": ajustes.AUTOMATICO}) == servidor.PELO_JOGO
    assert servidor.escolha_da_receita({}) == servidor.PELO_JOGO
