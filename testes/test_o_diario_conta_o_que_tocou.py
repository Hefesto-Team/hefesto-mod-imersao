"""O diário conta, a cada minuto em que houve jogo, o que tocou em cada controle e por que algo não
tocou, numa linha com os controles pela cor do plástico; o minuto sem jogo não escreve nada."""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, TRES, UM, EscritasDeMentira, PortaDeMentira, Recusa, ate
from apoio import vibracao_do_jogo as vibracao
from test_o_universal import TIQUE, som

import servidor
from motor import conta

JOGO = "steam_app_1"
MESA_MISTA = [
    {"uniq": UM, "jogador": 1, "cor": "Cosmic Red", "transporte": "usb"},
    {"uniq": DOIS, "jogador": 2, "cor": "Starlight Blue", "transporte": "bt"},
    {"uniq": TRES, "jogador": 3, "cor": "White", "transporte": "usb"},
    {"uniq": QUATRO, "jogador": 4, "cor": "Galactic Purple", "transporte": "bt"},
]
NATIVO = {"vence": "jogo", "modo": "nativo", "canal": "vibracao"}


class PortaQueConta(EscritasDeMentira):
    """A porta de mentira com os controles e as recusas da porta de verdade: o ``-32011`` do Modo
    Nativo a partir de ``nativo_desde`` nos controles de ``nativos``, e o ``-32015`` do som nos
    controles pelo rádio."""

    def __init__(self, controles: list[dict[str, Any]], nativos: frozenset[str] = frozenset(),
                 nativo_desde: float = 0.0) -> None:
        super().__init__(com_haptica=True, com_som=True)
        self.controles = controles
        self.nativos = nativos
        self.nativo_desde = nativo_desde

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "controles.lista":
            return {"controles": self.controles}
        if metodo in ("acessorios.estado", "eventos.assinar", "eventos.desassinar"):
            return {"status": "ok"}
        uniq = params.get("uniq")
        if (metodo == "vibracao.set" and uniq in self.nativos and self.agora >= self.nativo_desde
                and (params["forte"] or params["fraco"])):
            raise _Recusa("mais fraco que o jogo", -32011, NATIVO)
        radio = {c["uniq"] for c in self.controles if c.get("transporte") == "bt"}
        if metodo == "som.tocar" and uniq in radio:
            raise _Recusa("o rádio sem vaga na ponte", -32015, None)
        return await super().pedir(metodo, params)


class _Recusa(Recusa):
    def __init__(self, mensagem: str, codigo: int, dados: Any) -> None:
        super().__init__(mensagem, codigo)
        self.dados = dados


def _extensao(porta: PortaQueConta, jogo: str | None = JOGO) -> servidor.Extensao:
    extensao = servidor.Extensao(porta, servidor.carregar_o_universal())  # type: ignore[arg-type]
    asyncio.run(extensao.atualizar_os_controles())
    extensao.jogo = jogo
    return extensao


def _correr(extensao: servidor.Extensao, porta: PortaQueConta, ate_ms: float,
            eventos: list[tuple[float, Any]]) -> None:
    fila = sorted(eventos, key=lambda e: e[0])

    async def correr() -> None:
        k = 0
        while (t := k * TIQUE) <= ate_ms:
            while fila and fila[0][0] <= t + 1e-6:
                extensao.motor.evento(*fila.pop(0)[1])
            porta.agora = t
            await extensao.saida.aplicar(t, extensao.motor.passo(t))
            k += 1

    asyncio.run(correr())


def _resumo(extensao: servidor.Extensao, capsys: pytest.CaptureFixture[str]) -> list[str]:
    capsys.readouterr()
    extensao.fechar_o_minuto()
    return [linha for linha in capsys.readouterr().err.splitlines()
            if linha.startswith("resumo do minuto")]


def test_tres_efeitos_em_dois_controles_e_uma_recusa_dao_uma_linha_com_os_numeros(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueConta(MESA_MISTA[:2], frozenset({DOIS}), nativo_desde=600)
    extensao = _extensao(porta)
    _correr(extensao, porta, 1200, [(100, som("esquerdo", 0.4, 0.1)),
                                    (700, som("direito", 0.4, 0.7))])
    [linha] = _resumo(extensao, capsys)
    assert linha.endswith(": Cosmic Red tocou motores 2 | Starlight Blue tocou motores 1; "
                          "não tocou: nativo 1")
    assert "aa:bb" not in linha.lower()
    assert _resumo(extensao, capsys) == []


def test_o_minuto_sem_jogo_nao_escreve_e_o_com_jogo_parado_diz_que_nada_tocou(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueConta(MESA_MISTA[:1])
    sem_jogo = _extensao(porta, None)
    _correr(sem_jogo, porta, 600, [(100, som("esquerdo", 0.4, 0.1))])
    assert _resumo(sem_jogo, capsys) == []
    parado = _extensao(porta)
    _correr(parado, porta, 300, [])
    assert [linha.split(": ", 1)[1] for linha in _resumo(parado, capsys)] == [
        "Cosmic Red tocou nada"]


def test_os_quatro_juntos_na_mesa_mista_separados_pela_cor(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueConta(MESA_MISTA)
    extensao = _extensao(porta)
    tenso = [(t, ("microfone.nivel", "microfone.nivel", UM,
                  {"uniq": UM, "nivel": 0.01, "mudo": False, "do_jogo": False, "t": 0.0}))
             for t in range(0, 20_000, 500)]
    giro = [(t, ("movimento", "controle.movimento", UM, {
        "uniq": UM, "transporte": "bt", "giro": {"x": 0.0, "y": 0.0, "z": 3.0},
        "acel": {"x": 0.0, "y": 0.0, "z": 1.0}})) for t in range(0, 20_000, 400)]
    _correr(extensao, porta, 19_000, [*tenso, *giro, (18_000, som("direito", 0.45, 1234.5))])
    [linha] = _resumo(extensao, capsys)
    partes = linha.split(": ", 1)[1].split(" | ")
    assert [p.split(" tocou")[0] for p in partes] == [
        "Cosmic Red", "Starlight Blue", "White", "Galactic Purple"]
    for parte in partes:
        assert "alto-falante 1" in parte or "não tocou: sem_ponte 1" in parte
        assert "vibração fina" in parte
    assert sum("sem_ponte 1" in p for p in partes) == 2


def test_o_jogo_mais_forte_no_motor_conta_como_nao_tocou(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueConta(MESA_MISTA[:1])
    extensao = _extensao(porta)
    jogo_forte = [(t, ("jogo.vibracao", "jogo.vibracao", UM, vibracao(UM, 255, 255)))
                  for t in range(0, 600, 100)]
    _correr(extensao, porta, 500, [*jogo_forte, (200, som("esquerdo", 0.4, 0.2))])
    [linha] = _resumo(extensao, capsys)
    assert linha.endswith("; não tocou: jogo_mais_forte 1") and "motores" not in linha


def test_a_recusa_da_porta_se_le_pelo_motivo_que_ela_devolve() -> None:
    from motor.saida import motivo_da_recusa
    assert motivo_da_recusa(-32011, NATIVO) == "nativo"
    assert motivo_da_recusa(-32011, {"vence": "jogo"}) == "cedeu"
    assert motivo_da_recusa(-32011, {"vence": "extensao:outra"}) == "outra_extensao"
    assert motivo_da_recusa(-32011, {"motivo": "jogo_no_endpoint"}) == "jogo_no_endpoint"
    assert motivo_da_recusa(-32011, {"motivo": "Texto livre: com espaço"}) == "cedeu"
    assert motivo_da_recusa(-32015, None) == "sem_ponte"
    assert motivo_da_recusa(-32099, None) == "recusa_32099"


def test_o_resumo_para_no_teto_de_linhas(capsys: pytest.CaptureFixture[str],
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conta, "TETO_DE_RESUMOS", 2)
    porta = PortaQueConta(MESA_MISTA[:1])
    extensao = _extensao(porta)
    linhas = []
    for _ in range(4):
        _correr(extensao, porta, 50, [])
        linhas += _resumo(extensao, capsys)
    assert len(linhas) == 2 and linhas[-1].endswith("no teto de linhas")


class PortaQueLista(PortaQueConta):
    """A porta que conta os ``controles.lista``: a cor muda nela sem evento, como na de verdade."""

    def __init__(self, controles: list[dict[str, Any]]) -> None:
        super().__init__(controles)
        self.listas = 0

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.listas += metodo == "controles.lista"
        return await super().pedir(metodo, params)


def _nomes(extensao: servidor.Extensao, porta: PortaQueConta,
           capsys: pytest.CaptureFixture[str]) -> list[str]:
    _correr(extensao, porta, 50, [])
    [linha] = _resumo(extensao, capsys)
    return [p.split(" tocou")[0] for p in linha.split(": ", 1)[1].split(" | ")]


def test_a_cor_que_a_porta_le_depois_da_conexao_chega_ao_diario_e_ao_cartao(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueLista([{"uniq": UM, "jogador": 1, "transporte": "usb"}])
    extensao = _extensao(porta)
    assert _nomes(extensao, porta, capsys) == ["Jogador 1"]
    porta.controles = MESA_MISTA[:1]
    asyncio.run(extensao.rever_os_controles())
    assert _nomes(extensao, porta, capsys) == ["Cosmic Red"]
    assert [a["nome"] for a in extensao.aparelhos()] == ["Cosmic Red"]


def test_com_toda_cor_conhecida_a_lista_so_se_pede_de_novo_no_minuto(
        capsys: pytest.CaptureFixture[str]) -> None:
    porta = PortaQueLista([dict(c) for c in MESA_MISTA])
    extensao = _extensao(porta)
    antes = porta.listas
    asyncio.run(extensao.rever_os_controles())
    assert porta.listas == antes
    porta.controles[2]["cor"] = "Midnight Black"
    asyncio.run(extensao.rever_os_controles(sempre=True))
    assert porta.listas == antes + 1
    assert _nomes(extensao, porta, capsys) == [
        "Cosmic Red", "Starlight Blue", "Midnight Black", "Galactic Purple"]


def test_na_mesa_mista_o_controle_sem_cor_fica_pelo_jogador_e_os_outros_pela_cor(
        capsys: pytest.CaptureFixture[str]) -> None:
    sem_cor = {"uniq": DOIS, "jogador": 2, "transporte": "bt"}
    porta = PortaQueLista([MESA_MISTA[0], sem_cor, MESA_MISTA[2]])
    extensao = _extensao(porta)
    antes = porta.listas
    asyncio.run(extensao.rever_os_controles())
    assert porta.listas == antes + 1
    assert _nomes(extensao, porta, capsys) == ["Cosmic Red", "Jogador 2", "White"]
    assert [a["nome"] for a in extensao.aparelhos()] == ["Cosmic Red", "Jogador 2", "White"]


@pytest.fixture
def pasta_curta() -> Iterator[Path]:
    pasta = Path(tempfile.mkdtemp(prefix="cor-"))
    try:
        yield pasta
    finally:
        shutil.rmtree(pasta, ignore_errors=True)


def test_a_extensao_viva_pede_a_lista_ate_a_cor_chegar_e_de_novo_a_cada_minuto(
        pasta_curta: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(servidor, "RELE_OS_CONTROLES_S", 0.05)
    monkeypatch.setattr(servidor, "RESUMO_A_CADA_S", 1.0)
    monkeypatch.setenv("HEFESTO_MOD_SOCKET", str(pasta_curta / "mods.sock"))
    monkeypatch.setenv("HEFESTO_MOD_FICHA", "ficha-de-mentira")
    monkeypatch.delenv("HEFESTO_MOD_DADOS", raising=False)
    porta = PortaDeMentira([{"uniq": UM, "jogador": 1}])

    def nomes() -> list[list[str]]:
        return [[a["nome"] for a in e["aparelhos"]] for e in porta.de("acessorios.estado")]

    async def rodar() -> int:
        socket = await asyncio.start_unix_server(porta.atender, path=str(pasta_curta / "mods.sock"))
        extensoes: list[servidor.Extensao] = []
        processo = asyncio.create_task(servidor.rodar(extensoes.append))
        try:
            await ate(lambda: bool(extensoes))
            assert nomes()[-1] == ["Jogador 1"]
            porta.controles = [{"uniq": UM, "jogador": 1, "cor": "Cosmic Red"}]
            await ate(lambda: nomes()[-1] == ["Cosmic Red"], prazo=0.6)
            listas = porta.metodos.count("controles.lista")
            await asyncio.sleep(5 * servidor.RELE_OS_CONTROLES_S)
            assert porta.metodos.count("controles.lista") == listas
            porta.controles = [{"uniq": UM, "jogador": 1, "cor": "Midnight Black"}]
            await ate(lambda: nomes()[-1] == ["Midnight Black"])
            for escritor in porta.escritores:
                escritor.close()
            return await asyncio.wait_for(processo, 5)
        finally:
            socket.close()

    assert asyncio.run(rodar()) == 0
