"""Os caçadores do Estúdio guardam o que muda com o gesto e descartam o que muda sem ele.

A memória é sintética, de 1 MB: um trecho reescrito a cada retrato, um relógio que sobe sempre,
uma isca que desce também parada e um único inteiro que acompanha os gestos. O som é uma linha do
tempo de estalos com passos por toda parte e um estalo próprio perto de cada marca. A tela é uma
grade com um mapa que pisca sozinho, um clarão grande no meio e a barra de vida no canto.
"""
from __future__ import annotations

import asyncio
import base64
import json
import random
import struct
from pathlib import Path
from typing import Any

import pytest
from apoio import UM

import servidor
from estudio.cacador import (
    Achado,
    CacadorDeSom,
    CacadorDeTela,
    CacadorDeValor,
    Estudio,
    MemoriaDesligada,
    Retrato,
    VarredorDeRetratos,
    para_a_receita,
)
from motor.laco import Motor
from receita import impressao as impressoes
from receita.formato import ReceitaRecusada, ler_receita

JOGO = "steam_app_900000001"
TAMANHO = 1 << 20
RUIDO = range(0x10000, 0x11000)
ALVO, RELOGIO, ISCA = 0x40000, 0x50000, 0x60000
ROTEIRO = ("parado", "perder", "parado", "perder", "recuperar")


class Memoria:
    """A memória de mentira: o jogo anda um passo a cada gesto."""

    def __init__(self, com_alvo: bool = True, semente: int = 7) -> None:
        self.acaso = random.Random(semente)
        self.bytes = bytearray(self.acaso.randbytes(TAMANHO))
        self.com_alvo = com_alvo
        self.vida, self.isca, self.relogio = 100, 5000, 0
        self._gravar()

    def _gravar(self) -> None:
        self.bytes[RUIDO.start:RUIDO.stop] = self.acaso.randbytes(len(RUIDO))
        struct.pack_into("<i", self.bytes, ALVO, self.vida)
        struct.pack_into("<i", self.bytes, RELOGIO, self.relogio)
        struct.pack_into("<i", self.bytes, ISCA, self.isca)

    def passo(self, gesto: str) -> None:
        self.relogio += 1
        if gesto == "perder":
            self.vida -= 20 if self.vida == 100 else 25
            self.isca -= 3
        elif gesto == "recuperar":
            self.vida, self.isca = 100, self.isca + 50
        else:
            self.isca -= 1
        if not self.com_alvo:
            self.vida = 100
        self._gravar()

    def ler(self) -> bytes:
        return bytes(self.bytes)


async def _cacar(memoria: Memoria) -> CacadorDeValor:
    cacador = CacadorDeValor(VarredorDeRetratos(memoria.ler), memoria_ligada=True)
    await cacador.comecar()
    for gesto in ROTEIRO:
        memoria.passo(gesto)
        await cacador.gesto(gesto)
    return cacador


def test_o_valor_que_acompanha_os_gestos_sai_em_cinco_gestos_como_o_inteiro_mais_largo() -> None:
    cacador = asyncio.run(_cacar(Memoria()))
    achado = cacador.achado()
    assert achado is not None and len(cacador.gestos) <= 5
    assert (achado.dados["endereco"], achado.dados["tipo"], achado.dados["valor"]) == (
        hex(ALVO), "i32", 100)


def test_com_ruido_e_sem_valor_que_acompanhe_nada_se_acha() -> None:
    for semente in (1, 2, 3):
        assert asyncio.run(_cacar(Memoria(com_alvo=False, semente=semente))).achado() is None


def test_sem_a_chave_memoria_o_cacador_de_valor_nao_nasce_e_so_som_e_tela_aparecem() -> None:
    with pytest.raises(MemoriaDesligada):
        CacadorDeValor(VarredorDeRetratos(Memoria().ler), memoria_ligada=False)
    estudio = Estudio(_sem_porta, None, ler_receita)
    estudio.jogo = JOGO
    aberto = asyncio.run(estudio.mensagem({"tipo": "abrir"}, 0.0))
    assert aberto["cacadores"] == ["som", "tela"]
    recusa = asyncio.run(estudio.mensagem({"tipo": "comecar", "cacador": "valor"}, 0.0))
    assert recusa["tipo"] == "erro" and "Memória" in recusa["frase"]
    estudio.memoria_ligada = True
    assert asyncio.run(estudio.mensagem({"tipo": "abrir"}, 0.0))["cacadores"] == [
        "valor", "som", "tela"]


async def _sem_porta(metodo: str, params: dict[str, Any]) -> dict[str, Any]:
    raise RuntimeError(f"método desconhecido: {metodo}")


def _perfil(pico: int, largura: int, acaso: random.Random, mexe: float = 0.05) -> list[float]:
    return [max(0.0, 1.0 - abs(i - pico) / largura) + acaso.uniform(0, mexe) for i in range(24)]


def _linha_do_som(acaso: random.Random, marcas: list[float]) -> list[tuple[float, list[float]]]:
    linha = [(float(t), _perfil(18, 3, acaso)) for t in range(0, 26_000, 700)]
    linha += [(m - 800.0, _perfil(5, 2, acaso)) for m in marcas]
    linha += [(acaso.uniform(0, 26_000), [acaso.random() for _ in range(24)]) for _ in range(12)]
    return sorted(linha)


def _achar_o_som() -> Achado | None:
    acaso, marcas = random.Random(11), [5000.0, 12_000.0, 19_000.0]
    cacador = CacadorDeSom()
    for t, bandas in _linha_do_som(acaso, marcas):
        cacador.ouvir({"evento": "estalo", "lado": "centro", "energia": 0.4, "bandas": bandas}, t)
    for marca in marcas:
        cacador.marcar(marca)
    return cacador.achar()


def test_a_impressao_do_estalo_do_gesto_o_reconhece_de_novo_e_nao_reconhece_outro() -> None:
    achado = _achar_o_som()
    assert achado is not None
    impressao = achado.dados["impressao"]  # (noqa-acento)
    assert len(base64.b64decode(impressao["vetor"])) <= 4096
    acaso = random.Random(99)
    assert all(impressoes.reconhece(impressao, _perfil(5, 2, acaso)) for _ in range(5))
    assert not impressoes.reconhece(impressao, _perfil(18, 3, acaso))
    assert not impressoes.reconhece(impressao, _perfil(11, 2, acaso))


def test_poucas_marcas_ou_o_som_que_toca_sempre_nao_viram_impressao() -> None:
    acaso, cacador = random.Random(3), CacadorDeSom()
    for t in range(0, 20_000, 700):
        cacador.ouvir({"evento": "estalo", "bandas": _perfil(18, 3, acaso)}, float(t))
    cacador.marcar(5000.0)
    cacador.marcar(9000.0)
    assert cacador.achar() is None
    cacador.marcar(15_000.0)
    assert cacador.achar() is None


LARGURA, ALTURA = 64, 36


def _quadro(vida: int, mapa: int, clarao: bool) -> Retrato:
    pontos = bytearray(bytes((90, 90, 100)) * (LARGURA * ALTURA))

    def pintar(x0: int, y0: int, x1: int, y1: int, cor: tuple[int, int, int]) -> None:
        for y in range(y0, y1):
            for x in range(x0, x1):
                i = (y * LARGURA + x) * 3
                pontos[i:i + 3] = bytes(cor)

    pintar(52, 2, 62, 10, (mapa, 200 - mapa, 40))
    if clarao:
        pintar(12, 8, 52, 28, (250, 250, 250))
    pintar(2, 32, 22, 34, (30, 30, 30))
    pintar(2, 32, 2 + vida, 34, (200, 30, 30))
    return Retrato(LARGURA, ALTURA, bytes(pontos))


def _achar_a_tela() -> Achado | None:
    cacador = CacadorDeTela()
    cacador.guardar("cheia", _quadro(20, 10, False))
    cacador.guardar("parado", _quadro(20, 160, False))
    cacador.guardar("perder", _quadro(12, 60, True))
    return cacador.achar()


def test_o_canto_da_tela_e_o_que_muda_com_o_gesto_e_nao_o_que_pisca_sozinho() -> None:
    achado = _achar_a_tela()
    assert achado is not None
    regiao = achado.dados["regiao"]
    assert regiao["ancora"] == "canto_inf_esq"
    assert (regiao["x"], regiao["y"], regiao["w"], regiao["h"]) == pytest.approx(
        (14 / 64, 32 / 36, 8 / 64, 2 / 36), abs=1e-3)


def test_o_retrato_da_porta_fora_do_formato_e_recusado() -> None:
    with pytest.raises(ValueError):
        Retrato.da_porta({"largura": 4, "altura": 4, "rgb": base64.b64encode(b"x" * 10).decode()})


def _vale(dados: dict[str, Any]) -> Motor:
    return Motor(ler_receita(json.dumps(dados, ensure_ascii=False)))


def test_cada_achado_vira_um_estado_com_o_nome_dado_numa_receita_que_valida() -> None:
    valor = asyncio.run(_cacar(Memoria())).achado()
    som, tela = _achar_o_som(), _achar_a_tela()
    assert valor and som and tela
    receita = para_a_receita(None, JOGO, "Vida baixa", valor)
    receita = para_a_receita(receita, JOGO, "Golpe sofrido", som)
    receita = para_a_receita(receita, JOGO, "Barra caída", tela)
    motor = _vale(receita)
    assert set(motor.estados) == {"vida_baixa", "golpe_sofrido", "barra_caida"}
    assert receita["jogo"] == {"chave": JOGO, "leitura_de_memoria": "pede"}  # (noqa-acento)
    assert receita["sentidos"]["vida_baixa_lido"]["leitura"]["tipo"] == "i32"
    assert {"ler:jogo.memoria", "ler:jogo.som", "ler:jogo.tela"} <= set(
        receita["permissoes"])  # (noqa-acento)


def test_a_receita_le_o_som_pela_impressao_e_a_memoria_pelo_nome_do_sentido() -> None:
    som = _achar_o_som()
    assert som is not None
    receita = para_a_receita(None, JOGO, "Golpe", som)
    receita["sentidos"]["vida_lida"] = {
        "de": "jogo.memoria", "especie": "nivel", "escala": [0, 100],
        "leitura": {"tipo": "i32", "modulo": "jogo", "base": "0x40000"}}  # (noqa-acento)
    receita["estados"]["vida_baixa"] = {"quando": "vida_lida < 0.3"}
    receita["jogo"]["leitura_de_memoria"] = "pede"  # (noqa-acento)
    receita["permissoes"].append("ler:jogo.memoria")  # (noqa-acento)
    motor = _vale(receita)
    acaso = random.Random(5)
    motor.evento("jogo.som", "jogo.som", None, {"evento": "estalo", "bandas": _perfil(18, 3, acaso)})
    motor.evento("jogo.memoria", "jogo.memoria", None, {"vida_lida": 80, "t": 1.0})
    motor.passo(100.0)
    assert not motor.estados["golpe"].ligado and not motor.estados["vida_baixa"].ligado
    motor.evento("jogo.som", "jogo.som", None, {"evento": "estalo", "bandas": _perfil(5, 2, acaso)})
    motor.evento("jogo.memoria", "jogo.memoria", None, {"vida_lida": 20, "t": 2.0})
    motor.passo(200.0)
    assert motor.estados["golpe"].ligado and motor.estados["vida_baixa"].ligado


def test_a_impressao_e_a_regiao_fora_do_lugar_ou_grandes_demais_sao_recusadas() -> None:
    som, tela = _achar_o_som(), _achar_a_tela()
    assert som and tela
    errado = para_a_receita(None, JOGO, "x", som)
    errado["sentidos"]["x_lido"]["de"] = "jogo.tela"
    with pytest.raises(ReceitaRecusada, match="impressao"):  # (noqa-acento)
        ler_receita(json.dumps(errado))
    grande = para_a_receita(None, JOGO, "x", som)
    grande["sentidos"]["x_lido"]["impressao"] = impressoes.gravar([1.0] * 4097) | {  # (noqa-acento)
        "bandas": 64, "quadros": 64}
    with pytest.raises(ReceitaRecusada, match="teto"):
        ler_receita(json.dumps(grande))
    fora = para_a_receita(None, JOGO, "x", tela)
    fora["sentidos"]["x_lido"]["regiao"]["x"] = 0.95
    with pytest.raises(ReceitaRecusada, match="borda"):
        ler_receita(json.dumps(fora))


def test_o_estudio_guia_pelas_frases_caca_pelo_botao_e_guarda_na_receita_de_quem_joga(
        tmp_path: Path) -> None:
    memoria = Memoria()
    varredor = VarredorDeRetratos(memoria.ler)

    async def pedir(metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        assert metodo == "memoria.varrer"
        return await varredor.varrer(**params)

    async def corpo() -> list[dict[str, Any]]:
        estudio = Estudio(pedir, tmp_path / "receitas", ler_receita)
        estudio.jogo, estudio.memoria_ligada = JOGO, True
        respostas = [await estudio.mensagem({"tipo": "comecar", "cacador": "valor"}, 0.0)]
        for gesto in ROTEIRO:
            memoria.passo(gesto)
            respostas.append(await estudio.marca(0.0) or {})
        respostas.append(await estudio.mensagem({"tipo": "guardar", "nome": "Vida"}, 0.0))
        return respostas

    respostas = asyncio.run(corpo())
    assert [r.get("frase") for r in respostas[:5]] == [
        "agora não faça nada", "perca vida agora", "agora não faça nada", "perca vida agora",
        "recupere vida"]
    assert respostas[5]["tipo"] == "achou"
    assert respostas[6] == {"tipo": "guardado", "estado": "vida", "arquivo": JOGO + ".json"}
    guardada = ler_receita((tmp_path / "receitas" / (JOGO + ".json")).read_bytes())
    assert "vida" in guardada.secao("estados")


class _PortaDoEstudio:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []
        self.quadros = [_quadro(20, 10, False), _quadro(20, 160, False), _quadro(12, 60, True)]

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        if metodo == "tela.retrato":
            quadro = self.quadros.pop(0)
            return {"largura": quadro.largura, "altura": quadro.altura,
                    "rgb": base64.b64encode(quadro.rgb).decode("ascii")}
        return {"status": "ok"}


def test_a_pagina_fala_pelo_extensao_mensagem_e_o_botao_do_meio_marca_o_gesto(
        tmp_path: Path) -> None:
    porta = _PortaDoEstudio()

    async def corpo() -> None:
        extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     None, tmp_path)
        await extensao.ao_evento(_evento("perfil.jogo", "perfil.trocou",
                                         {"jogo": JOGO, "memoria": False}))
        await extensao.ao_evento(_evento("extensao.mensagem", "extensao.mensagem",
                                         {"id": 1, "dados": {"tipo": "abrir"}}))
        await extensao.ao_evento(_evento("extensao.mensagem", "extensao.mensagem",
                                         {"id": 2, "dados": {"tipo": "comecar",
                                                             "cacador": "tela"}}))
        for _ in range(3):
            await extensao.ao_evento(_evento("botoes", "button.down",
                                             {"button": "ps", "botao": "ps", "pressed": True,
                                              "uniq": UM, "jogador": 1}, UM))
        await extensao.ao_evento(_evento("extensao.mensagem", "extensao.mensagem",
                                         {"id": 3, "dados": {"tipo": "guardar",
                                                             "nome": "Barra"}}))

    asyncio.run(corpo())
    respostas = [p for m, p in porta.pedidos if m == "extensao.resposta"]
    assert respostas[0] == {"id": 1, "dados": {"tipo": "estudio", "jogo": JOGO,
                                               "cacadores": ["som", "tela"], "ativo": None}}
    assert [r["dados"].get("frase") for r in respostas[1:5]] == [
        "fique com a vida cheia", "agora não faça nada", "perca vida agora", "achei"]
    assert respostas[-1]["dados"]["tipo"] == "guardado"
    assert ("eventos.assinar", {"topicos": ["botoes"]}) in porta.pedidos
    assert ler_receita((tmp_path / "receitas" / (JOGO + ".json")).read_bytes()).secao("estados")


def _evento(topico: str, nome: str, dados: dict[str, Any],
            uniq: str | None = None) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": topico, "nome": nome, "uniq": uniq,
                                           "dados": dados}}


class VarredorDeUmSo:
    """A porta que acha um endereço só já na primeira varredura, em todo tipo."""

    async def varrer(self, tipo: str, comparacao: str, token: str | None = None,
                     valor: float | None = None) -> dict[str, Any]:
        return {"token": "t", "candidatos": 1, "endereco": hex(ALVO), "valor": 80}


@pytest.mark.parametrize(("gestos", "acha"), [
    (("parado", "perder"), False),
    (("perder", "perder"), False),
    (("parado", "perder", "perder"), True),
])
def test_o_endereco_unico_cedo_so_vale_com_dois_perder_e_um_parado(
        gestos: tuple[str, ...], acha: bool) -> None:
    async def cacar() -> CacadorDeValor:
        cacador = CacadorDeValor(VarredorDeUmSo(), memoria_ligada=True)
        await cacador.comecar()
        for gesto in gestos:
            await cacador.gesto(gesto)
        return cacador

    achado = asyncio.run(cacar()).achado()
    assert (achado is not None) is acha
