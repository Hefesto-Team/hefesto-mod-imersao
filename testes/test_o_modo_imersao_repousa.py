"""O Modo imersão repousa quando não há o que tocar.

Sem jogo em cena (dito pelo ``perfil.jogo``, no todo e em cada controle), sem efeito vivo, sem teste
pendente e com todo derivado em zero, o laço dorme até o primeiro evento, a mudança que o motor
sinaliza ou o prazo da renovação do ``corpo.ligar`` de cada controle. Com jogo em cena, os 60 Hz
seguem. A biblioteca de receitas não relê nem valida de novo o arquivo que não mudou no disco.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, QUATRO_CONTROLES, RAIZ, TRES, UM, EscritasDeMentira

import opcoes as ajustes
import servidor
from motor.laco import Motor, rodar
from motor.saida import RENOVA_MS, Saida
from receita import biblioteca as modulo_da_biblioteca
from receita.biblioteca import Biblioteca

UNIQS = (UM, DOIS, TRES, QUATRO)
SEM_JOGO: dict[str, Any] = {
    "perfil": "Padrão", "jogo": None, "em_cena": False, "estilo": None, "controles": [], "t": 1.0}


def _motor() -> Motor:
    motor = Motor(servidor.carregar_o_universal())
    motor.controles(QUATRO_CONTROLES)
    return motor


def _sem_jogo(motor: Motor, t_ms: float = 0.0) -> Motor:
    motor.evento("perfil.jogo", "perfil.trocou", None, dict(SEM_JOGO))
    motor.passo(t_ms)
    return motor


def _mesa(em_cena: str | None) -> dict[str, Any]:
    """O ``perfil.jogo`` da mesa misturada: o jogo só no controle ``em_cena``."""
    return {**SEM_JOGO, "controles": [
        {"jogador": j, "perfil": "Padrão", "jogo": "steam_app_1" if u == em_cena else None,
         "em_cena": u == em_cena, "estilo": None} for j, u in enumerate(UNIQS, 1)]}


def test_sem_o_perfil_jogo_o_motor_nao_repousa_e_depois_do_sem_jogo_repousa() -> None:
    motor = _motor()
    motor.passo(0.0)
    assert not motor.repousa()
    assert _sem_jogo(motor, 16.0).repousa()


@pytest.mark.parametrize("dono", UNIQS)
def test_o_jogo_em_cena_em_qualquer_controle_mantem_o_laco_acordado(dono: str) -> None:
    """D-2111-SEM-JOGO-EM-CENA-O-MOTOR-DO-IMERSAO-NAO-TICA-SOZINHO: o jogo em cena em qualquer
    controle da mesa mantém o laço acordado."""
    motor = _motor()
    motor.evento("perfil.jogo", "perfil.trocou", None, _mesa(dono))
    motor.passo(0.0)
    assert not motor.repousa()
    motor.evento("perfil.jogo", "perfil.trocou", None, _mesa(None))
    motor.passo(16.0)
    assert motor.repousa()


def test_o_jogo_em_cena_so_no_todo_mantem_o_laco_acordado() -> None:
    motor = _motor()
    motor.evento("perfil.jogo", "perfil.trocou", None, {**SEM_JOGO, "jogo": "steam_app_1",
                                                         "em_cena": True})
    motor.passo(0.0)
    assert not motor.repousa()


def test_o_efeito_vivo_e_o_evento_por_ler_mantem_o_laco_acordado() -> None:
    motor = _sem_jogo(_motor())
    assert motor.testar(ajustes.TESTES["testar_golpe"], 100.0)
    motor.passo(116.0)
    assert not motor.repousa()
    motor.passo(20000.0)
    assert motor.repousa()
    motor.evento("botoes", "button.down", UM, {"botao": "cross"})
    assert not motor.repousa()


class Contador:
    """O ``passo`` do motor que conta quantas vezes o laço o chamou."""

    def __init__(self, motor: Motor) -> None:
        self.chamadas = 0
        self._passo = motor.passo
        motor.passo = self.passo  # type: ignore[method-assign]

    def passo(self, t_ms: float) -> Any:
        self.chamadas += 1
        return self._passo(t_ms)


async def _correr_o_laco(motor: Motor, saida: Saida, corpo: Callable[[], Any]) -> None:
    parar = asyncio.Event()
    laco = asyncio.create_task(rodar(motor, saida, parar))
    try:
        await corpo()
    finally:
        parar.set()
        await asyncio.wait_for(laco, 3)


def test_em_repouso_o_passo_nao_roda_sem_evento_e_com_evento_roda_no_mesmo_tique() -> None:
    motor = _motor()
    contador = Contador(motor)
    saida = Saida(EscritasDeMentira().pedir)

    async def corpo() -> None:
        motor.evento("perfil.jogo", "perfil.trocou", None, dict(SEM_JOGO))
        await asyncio.sleep(0.1)
        antes = contador.chamadas
        await asyncio.sleep(0.4)
        assert contador.chamadas - antes <= 1
        for uniq in UNIQS:
            antes = contador.chamadas
            motor.evento("botoes", "button.down", uniq, {"botao": "cross"})
            await asyncio.sleep(0.1)
            assert contador.chamadas > antes

    asyncio.run(_correr_o_laco(motor, saida, corpo))


def test_com_jogo_em_cena_e_sem_evento_nenhum_o_laco_segue_a_60_hz() -> None:
    motor = _motor()
    contador = Contador(motor)
    saida = Saida(EscritasDeMentira().pedir)

    async def corpo() -> None:
        motor.evento("perfil.jogo", "perfil.trocou", None, _mesa(TRES))
        await asyncio.sleep(0.1)
        antes = contador.chamadas
        await asyncio.sleep(0.5)
        assert contador.chamadas - antes >= 15

    asyncio.run(_correr_o_laco(motor, saida, corpo))


def test_o_teste_pendente_mantem_o_laco_a_60_hz_mesmo_sem_jogo() -> None:
    motor = _motor()
    contador = Contador(motor)
    saida = Saida(EscritasDeMentira().pedir)
    pode = [False]

    async def corpo() -> None:
        motor.evento("perfil.jogo", "perfil.trocou", None, dict(SEM_JOGO))
        await asyncio.sleep(0.1)
        antes = contador.chamadas
        await asyncio.sleep(0.5)
        assert contador.chamadas - antes >= 15
        pode[0] = True

    async def correr() -> None:
        parar = asyncio.Event()
        laco = asyncio.create_task(rodar(motor, saida, parar, pode_repousar=lambda: pode[0]))
        try:
            await corpo()
        finally:
            parar.set()
            await asyncio.wait_for(laco, 3)

    asyncio.run(correr())


def test_o_motor_que_muda_acorda_o_laco_no_repouso() -> None:
    motor = _motor()
    contador = Contador(motor)
    saida = Saida(EscritasDeMentira().pedir)

    async def corpo() -> None:
        motor.evento("perfil.jogo", "perfil.trocou", None, dict(SEM_JOGO))
        await asyncio.sleep(0.1)
        mudancas: list[Callable[[], Any]] = [
            lambda: motor.controles(QUATRO_CONTROLES[:3]),
            lambda: motor.calar({TRES}),
            lambda: motor.nivelar({UM: (0.5, 0.5)}),
            lambda: motor.ajustar({"forca_geral": 50}),
            lambda: motor.estilo(),
        ]
        for mudar in mudancas:
            await asyncio.sleep(0.1)
            antes = contador.chamadas
            mudar()
            await asyncio.sleep(0.1)
            assert contador.chamadas > antes

    asyncio.run(_correr_o_laco(motor, saida, corpo))


def _corpo(uniq: str) -> dict[str, Any]:
    return {"som_no_corpo": 0.7}


def _a_saida_do_corpo(pedidos: dict[str, dict[str, Any]]) -> tuple[Saida, EscritasDeMentira]:
    porta = EscritasDeMentira()
    saida = Saida(porta.pedir)
    saida.pedidos_do_corpo = lambda: pedidos
    return saida, porta


def _corpos(porta: EscritasDeMentira) -> list[tuple[float, str, bool]]:
    return [(t, p["uniq"], "som_no_corpo" in p) for t, p in porta.de("corpo.ligar")]


def test_o_corpo_de_cada_controle_renova_no_prazo_dele_e_a_troca_de_transporte_nao_o_repete(
) -> None:
    pedidos = {u: _corpo(u) for u in UNIQS}
    saida, porta = _a_saida_do_corpo(pedidos)

    async def correr() -> list[float | None]:
        prazos: list[float | None] = []
        for t_ms in (0.0, 1000.0, 1200.0, 1400.0, RENOVA_MS):
            porta.agora = t_ms
            if t_ms == 1200.0:
                del pedidos[TRES]
            if t_ms == 1400.0:
                pedidos[TRES] = _corpo(TRES)
            prazos.append(saida.prazo_ms(t_ms))
            await saida.aplicar(t_ms, {})
            prazos.append(saida.prazo_ms(t_ms))
        return prazos

    prazos = asyncio.run(correr())
    assert prazos == [0.0, 2500.0, 1500.0, 1500.0, 0.0, 1300.0, 0.0, 1100.0, 0.0, 1400.0]
    assert _corpos(porta) == [
        (0.0, UM, True), (0.0, DOIS, True), (0.0, TRES, True), (0.0, QUATRO, True),
        (1200.0, TRES, False), (1400.0, TRES, True),
        (RENOVA_MS, UM, True), (RENOVA_MS, DOIS, True), (RENOVA_MS, QUATRO, True)]


def test_o_prazo_da_saida_e_o_da_renovacao_mais_proxima_e_sem_pedido_nao_ha_prazo() -> None:
    saida, porta = _a_saida_do_corpo({})
    assert saida.prazo_ms(0.0) is None
    saida.pedidos_do_corpo = None
    assert saida.prazo_ms(0.0) is None
    saida.pedidos_do_corpo = lambda: {UM: _corpo(UM)}
    assert saida.prazo_ms(0.0) == 0.0
    asyncio.run(saida.aplicar(100.0, {}))
    assert saida.prazo_ms(100.0) == RENOVA_MS
    assert saida.prazo_ms(2000.0) == RENOVA_MS - 1900.0
    assert saida.prazo_ms(RENOVA_MS + 500.0) == 0.0
    assert porta.de("corpo.ligar")[0][0] == 0.0


def test_a_escrita_viva_tira_o_prazo_e_depois_do_zero_nao_ha_prazo() -> None:
    from motor.arbitragem import Pedido

    saida, porta = _a_saida_do_corpo({})
    pedido = Pedido(UM, "motor", "esquerdo", "pulso", 1.0, 0, 0.0, 0, {"forca": 0.5})
    asyncio.run(saida.aplicar(0.0, {pedido.vaga: pedido}))
    assert saida.prazo_ms(0.0) == 0.0
    asyncio.run(saida.aplicar(16.0, {}))
    assert saida.prazo_ms(16.0) is None
    assert [p["forte"] for _, p in porta.de("vibracao.set")] == [128, 0]


@pytest.fixture
def pasta_curta() -> Iterator[Path]:
    pasta = Path(tempfile.mkdtemp(prefix="imj-"))
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


ESTUDADA = RAIZ / "receitas" / "estudadas" / "minecraft-dungeons-ii.json"


def _biblioteca(pasta: Path, quantas: int, diario: list[str] | None = None) -> Biblioteca:
    suas = pasta / "dados" / "receitas"
    suas.mkdir(parents=True)
    (pasta / "estudadas").mkdir()
    for n in range(quantas):
        shutil.copy(ESTUDADA, suas / f"r{n:03d}.json")
    return Biblioteca(pasta / "estudadas", pasta / "dados", servidor.carregar_o_universal,
                      (diario if diario is not None else []).append)


def _lidas(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    lidas: list[bytes] = []
    ler = modulo_da_biblioteca.ler_receita

    def contando(texto: bytes) -> Any:
        lidas.append(texto)
        return ler(texto)

    monkeypatch.setattr(modulo_da_biblioteca, "ler_receita", contando)
    return lidas


def test_a_biblioteca_com_200_receitas_nao_le_de_novo_o_que_nao_mudou(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    biblioteca = _biblioteca(pasta_curta, 200)
    lidas = _lidas(monkeypatch)
    inicio = time.perf_counter()
    biblioteca.para("nenhum")
    primeira = time.perf_counter() - inicio
    assert len(lidas) == 200
    tempos = []
    for _ in range(7):
        inicio = time.perf_counter()
        biblioteca.para("nenhum")
        tempos.append(time.perf_counter() - inicio)
    assert len(lidas) == 200
    assert min(tempos) < primeira / 10


def test_o_arquivo_que_muda_no_disco_e_relido_e_o_que_sai_do_disco_sai_da_conta(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    biblioteca = _biblioteca(pasta_curta, 3)
    lidas = _lidas(monkeypatch)
    arquivo = pasta_curta / "dados" / "receitas" / "r001.json"
    dados = json.loads(ESTUDADA.read_text(encoding="utf-8"))
    chave = dados["jogo"]["chave"]
    assert biblioteca.para("nenhum").origem == "universal"
    assert len(lidas) == 3
    assert biblioteca.para(chave).arquivo == pasta_curta / "dados" / "receitas" / "r000.json"
    assert len(lidas) == 3
    nova = "steam_app_900000009"
    dados["jogo"]["chave"] = nova
    arquivo.write_text(json.dumps(dados, indent=3), encoding="utf-8")
    assert biblioteca.para(nova).arquivo == arquivo
    assert len(lidas) == 4
    arquivo.unlink()
    assert biblioteca.para(nova).origem == "universal"
    assert len(lidas) == 4
    assert set(biblioteca._guardadas) == {pasta_curta / "dados" / "receitas" / f"r00{n}.json"
                                          for n in (0, 2)}


def test_a_receita_recusada_vai_ao_diario_uma_vez_por_versao_do_arquivo(
        pasta_curta: Path) -> None:
    diario: list[str] = []
    biblioteca = _biblioteca(pasta_curta, 1, diario)
    ruim = pasta_curta / "dados" / "receitas" / "ruim.json"
    ruim.write_text("{", encoding="utf-8")
    for _ in range(3):
        biblioteca.para("nenhum")
    assert sum("ruim.json" in linha for linha in diario) == 1
    ruim.write_text("[1, 2]", encoding="utf-8")
    biblioteca.para("nenhum")
    assert sum("ruim.json" in linha for linha in diario) == 2


def test_a_gravacao_do_opcoes_so_escolhe_a_receita_de_novo_quando_a_opcao_receita_mudou(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dados = pasta_curta / "dados"
    dados.mkdir()
    chamadas: list[tuple[str | None, str]] = []
    biblioteca = Biblioteca(pasta_curta / "estudadas", dados, servidor.carregar_o_universal)
    para = biblioteca.para

    def contando(chave: str | None, escolha: str = "Pelo jogo") -> Any:
        chamadas.append((chave, escolha))
        return para(chave, escolha)

    monkeypatch.setattr(biblioteca, "para", contando)
    extensao = servidor.Extensao(_PortaMuda(), para(None), biblioteca, dados)  # type: ignore[arg-type]
    opcoes = dados / servidor.ARQUIVO_DAS_OPCOES

    async def correr() -> None:
        opcoes.write_text(json.dumps({"forca_geral": 40}), encoding="utf-8")
        await extensao.reler_as_opcoes()
        assert chamadas == []
        opcoes.write_text(json.dumps({"forca_geral": 40,
                                      ajustes.AJUSTE: ajustes.SEMPRE_O_UNIVERSAL}),
                          encoding="utf-8")
        await extensao.reler_as_opcoes()
        assert chamadas == [(None, "Universal")]
        await extensao.reler_as_opcoes()
        assert len(chamadas) == 1

    asyncio.run(correr())


class _PortaMuda:
    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok"}
