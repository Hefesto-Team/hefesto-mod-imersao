"""A Força e o volume de cada controle, chamados pela cor do plástico, lado a lado na aba Jogo:
valem juntos (uma barra não mexe na outra) e vezes a Força geral, de um a quatro controles, na mesa
mista de cabo e rádio, e ficam guardados no ``controles.json``."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, TRES, UM, EscritasDeMentira, Recusa
from test_o_universal import TIQUE, microfone, na_mao, som

import opcoes as ajustes
import servidor

MESA_MISTA = [
    {"uniq": UM, "jogador": 1, "cor": "Cosmic Red", "transporte": "usb"},
    {"uniq": DOIS, "jogador": 2, "cor": "Starlight Blue", "transporte": "bt"},
    {"uniq": TRES, "jogador": 3, "cor": "White", "transporte": "usb"},
    {"uniq": QUATRO, "jogador": 4, "cor": "Galactic Purple", "transporte": "bt"},
]
SUSTO = ([(t, microfone(UM, 0.01)) for t in range(0, 20_000, 500)] + na_mao(UM, 20_000)
         + [(18_000, som("direito", 0.45, 1234.5))])


class PortaDaMesa(EscritasDeMentira):
    def __init__(self, controles: list[dict[str, Any]],
                 sem_ponte: frozenset[str] = frozenset()) -> None:
        super().__init__(com_haptica=True, com_som=True)
        self.controles = controles
        self.sem_ponte = sem_ponte
        self.estados: list[dict[str, Any]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if metodo == "controles.lista":
            return {"controles": self.controles}
        if metodo == "acessorios.estado":
            self.estados.append(params)
            return {"status": "ok"}
        if metodo in ("eventos.assinar", "eventos.desassinar"):
            return {"status": "ok"}
        if metodo == "som.tocar" and params["uniq"] in self.sem_ponte:
            raise Recusa("o rádio sem vaga na ponte", -32015)
        return await super().pedir(metodo, params)


def _acao(acao: str, alvo: str, valor: str) -> dict[str, Any]:
    return {"method": "evento", "params": {
        "topico": "extensao.acao", "nome": "extensao.acao", "uniq": None,
        "dados": {"mod": "imersao", "acao": acao, "alvo": alvo, "valor": valor}}}


def _extensao(porta: PortaDaMesa, dados: Path,
              gestos: list[tuple[str, str, str]] | None = None) -> servidor.Extensao:
    async def montar() -> servidor.Extensao:
        extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     None, dados)
        await extensao.atualizar_os_controles()
        await extensao.publicar_o_estado()
        for gesto in gestos or []:
            await extensao.ao_evento(_acao(*gesto))
        return extensao
    return asyncio.run(montar())


def _correr(extensao: servidor.Extensao, porta: PortaDaMesa, ate_ms: float,
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


def _susto(porta: PortaDaMesa, uniq: str) -> float:
    return max((p["forca"] for _, p in porta.de("haptica.tocar")
                if p["uniq"] == uniq and p["id"] == "susto"), default=0.0)  # (noqa-acento)


def _volume(porta: PortaDaMesa, uniq: str) -> float | None:
    return next((p["volume"] for _, p in porta.de("som.tocar") if p["uniq"] == uniq), None)


def test_cada_cartao_pela_cor_leva_a_forca_e_o_volume_lado_a_lado(tmp_path: Path) -> None:
    porta = PortaDaMesa(MESA_MISTA)
    _extensao(porta, tmp_path)
    aparelhos = porta.estados[-1]["aparelhos"]
    assert [a["nome"] for a in aparelhos] == [c["cor"] for c in MESA_MISTA]
    for aparelho in aparelhos:
        assert [(c["id"], c["rotulo"], c["tipo"], c["valor"]) for c in aparelho["controles"]] == [
            ("forca", "Força", "escolha", "100"), ("volume", "Volume", "escolha", "100")]
        assert all(len(c["rotulo"]) <= 6 and c["dica"] for c in aparelho["controles"])
    do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.porta")
    manifesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto").ler_manifesto(
        servidor.AQUI)
    assert manifesto.aparelhos_controles.grupo == "Jogo"
    validado = do_hefesto.estado_dos_acessorios("imersao", porta.estados[-1],
                                                acoes_dos_aparelhos=frozenset({"ligar"}))
    assert len(validado["aparelhos"]) == 4


def test_a_forca_e_o_volume_de_cada_controle_valem_juntos_sem_uma_anular_a_outra(
        tmp_path: Path) -> None:
    porta = PortaDaMesa(MESA_MISTA)
    extensao = _extensao(porta, tmp_path, [
        ("forca", "jogador-1", "0"), ("forca", "jogador-2", "50"),
        ("volume", "jogador-3", "25"), ("volume", "jogador-4", "0")])
    _correr(extensao, porta, 19_000, SUSTO)
    assert _susto(porta, UM) == 0.0 and _volume(porta, UM) == 1.0
    assert _susto(porta, DOIS) == 0.5 and _volume(porta, DOIS) == 1.0
    assert _susto(porta, TRES) == 1.0 and _volume(porta, TRES) == 0.25
    assert _susto(porta, QUATRO) == 1.0 and _volume(porta, QUATRO) is None
    guardado = json.loads((tmp_path / ajustes.ARQUIVO_DOS_CONTROLES).read_text(encoding="utf-8"))
    assert guardado == {"calados": [], "forca": {"jogador-1": 0, "jogador-2": 50},
                        "volume": {"jogador-3": 25, "jogador-4": 0}}


def test_a_forca_geral_multiplica_a_do_controle(tmp_path: Path) -> None:
    (tmp_path / "opcoes.json").write_text(json.dumps({"forca_geral": 50}), encoding="utf-8")
    porta = PortaDaMesa(MESA_MISTA[:2])
    extensao = _extensao(porta, tmp_path, [("forca", "jogador-2", "50"),
                                           ("volume", "jogador-2", "50")])
    _correr(extensao, porta, 19_000, SUSTO)
    assert (_susto(porta, UM), _volume(porta, UM)) == (0.5, 0.5)
    assert (_susto(porta, DOIS), _volume(porta, DOIS)) == (0.25, 0.25)


def test_o_buraco_na_mesa_e_o_radio_sem_ponte_nao_mudam_o_nivel_dos_outros(
        tmp_path: Path) -> None:
    mesa = [MESA_MISTA[0], MESA_MISTA[3]]
    porta = PortaDaMesa(mesa, sem_ponte=frozenset({QUATRO}))
    extensao = _extensao(porta, tmp_path, [("volume", "jogador-1", "75"),
                                           ("forca", "jogador-4", "25")])
    _correr(extensao, porta, 19_000, SUSTO)
    assert (_susto(porta, UM), _volume(porta, UM)) == (1.0, 0.75)
    assert _susto(porta, QUATRO) == 0.25 and _volume(porta, QUATRO) is None


def test_o_nivel_fica_guardado_com_os_calados_e_o_torto_nao_muda_nada(tmp_path: Path) -> None:
    porta = PortaDaMesa(MESA_MISTA)
    extensao = _extensao(porta, tmp_path, [
        ("forca", "jogador-2", "75"), ("ligar", "jogador-3", "x"),
        ("forca", "jogador-2", "33"), ("volume", "jogador-1", "muito"),
        ("volume", "aa:bb:cc:00:00:01", "50"), ("brilho", "jogador-1", "50")])
    asyncio.run(extensao.sentir("jogador-3", False))
    de_novo = _extensao(PortaDaMesa(MESA_MISTA), tmp_path)
    assert de_novo.niveis == {"forca": {"jogador-2": 75}, "volume": {}}
    assert de_novo.calados == frozenset({"jogador-3"})
    cartao = next(a for a in de_novo.aparelhos() if a["id"] == "jogador-2")
    assert [c["valor"] for c in cartao["controles"]] == ["75", "100"]
    assert all("aa:bb" not in json.dumps(a) for a in de_novo.aparelhos())
