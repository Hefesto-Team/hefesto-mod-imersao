"""As receitas da comunidade só entram com o índice assinado, e a memória espera a chave do Hefesto.

O índice com a assinatura errada se recusa e nada mais se baixa; a receita trocada depois do CI se
recusa pela soma; a receita que lê a memória diz isso à página e espera a chave «Memória neste
jogo» do Hefesto, sem chave própria. A sua e a estudada vencem a da comunidade, e a tela diz de
onde veio a que vale.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from apoio import RAIZ

import comunidade
import opcoes as ajustes
import servidor
from comunidade import (
    ENDERECO,
    RECUOS_S,
    UM_DIA_S,
    AssinaturaRecusada,
    Comunidade,
    assinar_ed25519,
    assinar_minisign,
    chave_publica_minisign,
    conferir_ed25519,
    conferir_minisign,
    ler_o_indice,
    publica_da_semente,
)
from receita.biblioteca import Biblioteca

SEMENTE = bytes(range(32))
OUTRA = bytes(range(1, 33))
IDENT = b"provas00"
PUBLICA = chave_publica_minisign(SEMENTE, IDENT)
JOGO = "steam_app_900000003"
ESTUDADO = "steam_app_1912410"


def _receita(chave: str = JOGO, memoria: bool = False) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "formato": 1, "motor": ">=1,<2", "jogo": {"chave": chave},
        "permissoes": ["ler:jogo.vibracao"],  # (noqa-acento)
        "sentidos": {"rumble": {"de": "jogo.vibracao", "especie": "nivel",
                                "campo": "pedido.1", "escala": [0, 255]}},
        "efeitos": {"tranco": {"canal": "motor", "forca": 1.0, "lado": "esquerdo"}},
        "regras": [{"quando": "rumble > 0.5", "entao": "tranco"}]}
    if memoria:
        dados["jogo"]["leitura_de_memoria"] = "pede"  # (noqa-acento)
        dados["permissoes"].append("ler:jogo.memoria")  # (noqa-acento)
        dados["sentidos"]["vida_lida"] = {
            "de": "jogo.memoria", "especie": "nivel", "escala": [0, 100],
            "leitura": {"tipo": "i32", "modulo": "jogo", "base": "0x40000"}}  # (noqa-acento)
        dados["estados"] = {"vida_baixa": {"quando": "vida_lida < 0.3"}}
        dados["regras"].append({"quando": "vida_baixa", "entao": "tranco"})
    return dados


class Repositorio:
    """O repositório de mentira: o que ``baixar`` serve e os endereços pedidos."""

    def __init__(self, receitas: dict[str, dict[str, Any]], semente: bytes = SEMENTE,
                 anticheat: tuple[str, ...] = ()) -> None:
        self.arquivos: dict[str, bytes] = {}
        itens = []
        for arquivo, receita in receitas.items():
            bruto = json.dumps(receita, ensure_ascii=False, indent=2).encode("utf-8")
            self.arquivos[arquivo] = bruto
            chave = receita["jogo"]["chave"]
            itens.append({"chave": chave, "arquivo": arquivo, "tamanho": len(bruto),
                          "sha256": hashlib.sha256(bruto).hexdigest(),
                          "memoria": receita["jogo"].get("leitura_de_memoria") == "pede",  # (noqa-acento)
                          "anticheat": chave in anticheat})
        indice = json.dumps({"formato": 1, "receitas": itens}).encode("utf-8")
        self.arquivos["indice.json"] = indice
        self.arquivos["indice.json.minisig"] = assinar_minisign(
            semente, IDENT, indice, "indice de provas").encode("utf-8")
        self.pedidos: list[str] = []

    def baixar(self, endereco: str, teto: int) -> bytes:
        self.pedidos.append(endereco.removeprefix(ENDERECO))
        corpo = self.arquivos[endereco.removeprefix(ENDERECO)]
        if len(corpo) > teto:
            raise ValueError("passa do teto")
        return corpo


def _comunidade(tmp_path: Path, repositorio: Repositorio, agora: float = 1e9) -> Comunidade:
    return Comunidade(tmp_path, repositorio.baixar, PUBLICA, lambda: agora)


ARQUIVO = f"steam/{JOGO}/golpe-forte.json"


def test_o_ed25519_puro_bate_com_a_rfc_8032() -> None:
    semente = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    publica = publica_da_semente(semente)
    assert publica.hex() == "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
    assinatura = assinar_ed25519(semente, b"\x72")
    assert assinatura.hex() == (
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00")
    assert conferir_ed25519(publica, b"\x72", assinatura)
    assert not conferir_ed25519(publica, b"\x73", assinatura)
    torta = bytearray(assinatura)
    torta[40] ^= 1
    assert not conferir_ed25519(publica, b"\x72", bytes(torta))


def test_o_ed25519_puro_bate_com_a_biblioteca_de_referencia() -> None:
    ed = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")
    chave = ed.Ed25519PrivateKey.from_private_bytes(SEMENTE)
    for mensagem in (b"", b"indice", bytes(range(200))):
        assert assinar_ed25519(SEMENTE, mensagem) == chave.sign(mensagem)


def test_o_minisig_fecha_e_qualquer_troca_recusa() -> None:
    indice = b'{"formato": 1, "receitas": []}'
    minisig = assinar_minisign(SEMENTE, IDENT, indice, "gerado em 02/11/2026").encode()
    assert conferir_minisign(indice, minisig, PUBLICA) == "gerado em 02/11/2026"
    with pytest.raises(AssinaturaRecusada, match="não fecha"):
        conferir_minisign(indice + b" ", minisig, PUBLICA)
    trocado = minisig.replace(b"gerado em 02/11/2026", b"gerado em 03/11/2026")
    with pytest.raises(AssinaturaRecusada, match="confiança"):
        conferir_minisign(indice, trocado, PUBLICA)
    with pytest.raises(AssinaturaRecusada, match="outra chave"):
        conferir_minisign(indice, minisig, chave_publica_minisign(OUTRA, b"outra000"))
    with pytest.raises(AssinaturaRecusada):
        conferir_minisign(indice, b"lixo", PUBLICA)
    assert comunidade.CHAVE_PUBLICA != PUBLICA


def test_a_receita_do_indice_assinado_chega_e_vale_depois_da_sua_e_da_estudada(
        tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita(),
                               f"steam/{ESTUDADO}/outra.json": _receita(ESTUDADO)})
    resultado = _comunidade(tmp_path, repositorio).procurar(JOGO, agora=True)
    assert resultado["tipo"] == "procurado" and resultado["achou"] and resultado["nova"]
    assert repositorio.pedidos == ["indice.json", "indice.json.minisig", ARQUIVO]
    biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                            servidor.carregar_o_universal)
    assert biblioteca.para(JOGO).origem == "comunidade"
    assert biblioteca.para(JOGO).rotulo == "Receita da comunidade"
    _comunidade(tmp_path, repositorio).procurar(ESTUDADO)
    assert biblioteca.para(ESTUDADO).origem == "estudada"
    (tmp_path / "receitas").mkdir()
    (tmp_path / "receitas" / "minha.json").write_text(json.dumps(_receita()), "utf-8")
    assert biblioteca.para(JOGO).origem == "sua"


def test_o_indice_com_a_assinatura_errada_recusa_e_nada_se_baixa(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita()}, semente=OUTRA)
    resultado = _comunidade(tmp_path, repositorio).procurar(JOGO, agora=True)
    assert resultado["tipo"] == "recusado"
    assert repositorio.pedidos == ["indice.json", "indice.json.minisig"]
    assert not (tmp_path / "comunidade").exists()
    assert not (tmp_path / "indice-da-comunidade").exists()


def test_o_indice_trocado_depois_de_assinado_recusa(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita()})
    repositorio.arquivos["indice.json"] = repositorio.arquivos["indice.json"].replace(
        b'"anticheat": false', b'"anticheat": true')
    assert _comunidade(tmp_path, repositorio).procurar(JOGO, agora=True)["tipo"] == "recusado"
    assert ARQUIVO not in repositorio.pedidos


def test_a_receita_trocada_depois_do_ci_recusa_pela_soma(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita()})
    trocada = repositorio.arquivos[ARQUIVO].replace(b'"forca": 1.0', b'"forca": 0.1')
    repositorio.arquivos[ARQUIVO] = trocada
    resultado = _comunidade(tmp_path, repositorio).procurar(JOGO, agora=True)
    assert resultado["tipo"] == "recusado" and "soma" in resultado["frase"]
    assert not (tmp_path / "comunidade").exists()


def test_a_receita_que_esconde_a_memoria_do_indice_recusa(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita(memoria=True)})
    indice = json.loads(repositorio.arquivos["indice.json"])
    indice["receitas"][0]["memoria"] = False
    bruto = json.dumps(indice).encode()
    repositorio.arquivos["indice.json"] = bruto
    repositorio.arquivos["indice.json.minisig"] = assinar_minisign(
        SEMENTE, IDENT, bruto, "x").encode()
    resultado = _comunidade(tmp_path, repositorio).procurar(JOGO, agora=True)
    assert resultado["tipo"] == "recusado" and "memória" in resultado["frase"]


def test_o_indice_se_baixa_uma_vez_por_dia_e_o_botao_o_baixa_na_hora(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita()})
    assert _comunidade(tmp_path, repositorio).vencido()
    _comunidade(tmp_path, repositorio).procurar(JOGO)
    agora = (tmp_path / "indice-da-comunidade" / "indice.json").stat().st_mtime
    repositorio.pedidos.clear()
    assert not _comunidade(tmp_path, repositorio, agora + 60).vencido()
    _comunidade(tmp_path, repositorio, agora + 60).procurar(JOGO)
    assert repositorio.pedidos == []
    _comunidade(tmp_path, repositorio, agora + 60).procurar(JOGO, agora=True)
    assert repositorio.pedidos == ["indice.json", "indice.json.minisig"]
    agora = (tmp_path / "indice-da-comunidade" / "indice.json").stat().st_mtime
    assert not _comunidade(tmp_path, repositorio, agora + UM_DIA_S - 1).vencido()
    assert _comunidade(tmp_path, repositorio, agora + UM_DIA_S).vencido()


def test_o_indice_guardado_se_confere_de_novo_a_cada_leitura(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita()})
    aqui = _comunidade(tmp_path, repositorio)
    aqui.atualizar_o_indice()
    assert aqui.entrada_do_jogo(JOGO) is not None
    guardado = tmp_path / "indice-da-comunidade" / "indice.json"
    guardado.write_bytes(guardado.read_bytes().replace(b"golpe-forte", b"golpe-fraco"))
    assert aqui.entradas() == []
    with pytest.raises(AssinaturaRecusada):
        ler_o_indice(guardado.read_bytes(), repositorio.arquivos["indice.json.minisig"], PUBLICA)


def test_a_receita_que_le_a_memoria_nao_traz_chave_propria(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita(memoria=True)}, anticheat=(JOGO,))
    aqui = _comunidade(tmp_path, repositorio)
    resultado = aqui.procurar(JOGO, agora=True)
    assert resultado["memoria"] is True
    assert not {"memoria_ligada", "anticheat"} & set(resultado)
    assert not hasattr(aqui, "ligar_a_memoria")
    assert not list(tmp_path.rglob("memoria.json"))


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"status": "ok"}


def _evento(topico: str, dados: dict[str, Any]) -> dict[str, Any]:
    return {"method": "evento", "params": {"topico": topico, "nome": topico, "uniq": None,
                                           "dados": dados}}


def test_o_jogo_que_abre_traz_a_receita_e_a_memoria_so_chega_ao_motor_com_a_chave_do_hefesto(
        tmp_path: Path) -> None:
    porta = _Porta()
    repositorio = Repositorio({ARQUIVO: _receita(memoria=True)}, anticheat=(JOGO,))

    async def corpo() -> tuple[list[str], list[Any], list[dict[str, Any]]]:
        biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                                servidor.carregar_o_universal)
        extensao = servidor.Extensao(porta, servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     biblioteca, tmp_path, _comunidade(tmp_path, repositorio))
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO, "memoria": False}))
        assert extensao.procurando is not None
        await asyncio.wait_for(extensao.procurando, 5)
        origens = [extensao.escolhida.origem]
        vistos: list[Any] = []
        extensao.motor.evento = lambda *a: vistos.append(a)  # type: ignore[method-assign]
        respostas: list[dict[str, Any]] = []

        async def procurar() -> None:
            extensao.procurar_em_fundo(agora=True)
            assert extensao.procurando is not None
            respostas.append(await asyncio.wait_for(extensao.procurando, 5))

        await extensao.ao_evento(_evento("jogo.memoria", {"vida_lida": 10}))
        await procurar()
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO, "memoria": True}))
        await asyncio.wait_for(extensao.procurando, 5)
        await extensao.ao_evento(_evento("jogo.memoria", {"vida_lida": 11}))
        await procurar()
        origens.append(extensao.escolhida.origem)
        return origens, vistos, respostas

    origens, vistos, respostas = asyncio.run(corpo())
    assert origens == ["comunidade", "comunidade"]
    assert [v[3] for v in vistos if v[0] == "jogo.memoria"] == [{"vida_lida": 11}]
    assert [(r["tipo"], r["memoria"], r["memoria_ligada"]) for r in respostas] == [
        ("procurado", True, False), ("procurado", True, True)]
    assert respostas[0]["origem"] == "Receita da comunidade"
    estados = [p["perfil"] for m, p in porta.pedidos if m == "acessorios.estado"]
    assert estados[-1] == "Receita da comunidade"
    assert not list(tmp_path.rglob("memoria.json"))


def test_a_receita_que_sai_do_indice_assinado_sai_do_disco_e_volta_a_estudada_ou_o_universal(
        tmp_path: Path) -> None:
    _comunidade(tmp_path, Repositorio({ARQUIVO: _receita()})).procurar(JOGO, agora=True)
    biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                            servidor.carregar_o_universal)
    assert biblioteca.para(JOGO).origem == "comunidade"
    resultado = _comunidade(tmp_path, Repositorio({})).procurar(JOGO, agora=True)
    assert resultado == {"tipo": "procurado", "achou": False}
    assert biblioteca.para(JOGO).origem == "universal"


def test_sem_internet_a_receita_baixada_fica_e_a_tela_nao_ve_o_erro_cru(tmp_path: Path) -> None:
    _comunidade(tmp_path, Repositorio({ARQUIVO: _receita()})).procurar(JOGO, agora=True)

    def sem_rede(_endereco: str, _teto: int) -> bytes:
        raise OSError("[Errno -3] Temporary failure in name resolution")

    resultado = Comunidade(tmp_path, sem_rede, PUBLICA, lambda: 1e9).procurar(JOGO, agora=True)
    assert resultado["tipo"] == "erro" and "Errno" not in resultado["frase"]
    assert "Errno" in resultado["detalhe"]
    assert (tmp_path / "comunidade" / f"{JOGO}.json").is_file()


class _Rede:
    """O servidor de mentira: o endereço pedido e se ele responde (``404``) ou serve o repositório."""

    def __init__(self, repositorio: Repositorio | None = None, no_ar: bool = False) -> None:
        self.repositorio = repositorio
        self.no_ar = no_ar
        self.pedidos: list[str] = []

    def baixar(self, endereco: str, teto: int) -> bytes:
        self.pedidos.append(endereco.removeprefix(ENDERECO))
        if not self.no_ar or self.repositorio is None:
            raise OSError("HTTP Error 404: Not Found")
        return self.repositorio.baixar(endereco, teto)


def test_a_falha_do_indice_da_espera_crescente_e_o_indice_que_vem_zera_a_espera(
        tmp_path: Path) -> None:
    """D-2511-A-BUSCA-DAS-RECEITAS-RECUA-QUANDO-FALHA-E-RESPEITA-O-UNIVERSAL: o recuo da falha."""
    rede = _Rede(Repositorio({ARQUIVO: _receita()}))
    agora = [time.time()]
    aqui = Comunidade(tmp_path, rede.baixar, PUBLICA, lambda: agora[0])

    def tentar() -> str:
        antes = len(rede.pedidos)
        tipo = str(aqui.procurar(JOGO)["tipo"])
        return f"{tipo}:{len(rede.pedidos) - antes}"

    assert [tentar(), tentar(), tentar()] == ["erro:1", "procurado:0", "procurado:0"]
    for espera in (RECUOS_S[0], RECUOS_S[1], RECUOS_S[2], RECUOS_S[2]):
        agora[0] += espera - 1
        assert tentar() == "procurado:0"
        agora[0] += 1
        assert tentar() == "erro:1"
    rede.no_ar = True
    agora[0] += RECUOS_S[-1]
    assert tentar() == "procurado:3"
    agora[0] += UM_DIA_S
    rede.no_ar = False
    assert tentar() == "erro:1"
    agora[0] += RECUOS_S[0]
    assert tentar() == "erro:1"


def test_tres_jogos_seguidos_com_o_servidor_fora_fazem_um_pedido_e_uma_linha_no_diario(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rede = _Rede()
    agora = [time.time()]
    aqui = Comunidade(tmp_path, rede.baixar, PUBLICA, lambda: agora[0])

    async def corpo() -> None:
        extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     None, tmp_path, aqui)
        for _ in range(3):
            await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO, "memoria": False}))
            assert extensao.procurando is not None
            await asyncio.wait_for(extensao.procurando, 5)
        agora[0] += RECUOS_S[0]
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO, "memoria": False}))
        assert extensao.procurando is not None
        await asyncio.wait_for(extensao.procurando, 5)

    asyncio.run(corpo())
    assert rede.pedidos == ["indice.json", "indice.json"]
    assert capsys.readouterr().err.count("as receitas da comunidade não vieram") == 2


def test_em_sempre_o_universal_nao_se_busca_e_ao_voltar_ao_jogo_a_busca_sai(
        tmp_path: Path) -> None:
    rede = _Rede(Repositorio({ARQUIVO: _receita()}), no_ar=True)

    async def corpo() -> None:
        biblioteca = Biblioteca(RAIZ / "receitas" / "estudadas", tmp_path,
                                servidor.carregar_o_universal)
        extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     biblioteca, tmp_path,
                                     Comunidade(tmp_path, rede.baixar, PUBLICA))
        extensao.opcoes = {**extensao.opcoes, ajustes.AJUSTE: ajustes.SEMPRE_O_UNIVERSAL}
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO, "memoria": False}))
        assert extensao.procurando is None
        assert rede.pedidos == []
        extensao.dados = tmp_path
        (tmp_path / "opcoes.json").write_text(json.dumps({ajustes.AJUSTE: ajustes.AUTOMATICO}))
        await extensao.reler_as_opcoes()
        busca: Any = extensao.procurando
        assert busca is not None
        await asyncio.wait_for(busca, 5)

    asyncio.run(corpo())
    assert rede.pedidos == ["indice.json", "indice.json.minisig", ARQUIVO]


def test_o_jogo_que_abre_durante_a_busca_do_anterior_ganha_a_busca_dele(tmp_path: Path) -> None:
    outro = "steam_app_900000005"
    arquivo_do_outro = f"steam/{outro}/golpe-forte.json"
    repositorio = Repositorio({ARQUIVO: _receita(), arquivo_do_outro: _receita(outro)})
    entrou, liberar = threading.Event(), threading.Event()

    def baixar(endereco: str, teto: int) -> bytes:
        if not liberar.is_set():
            entrou.set()
            liberar.wait(5)
        return repositorio.baixar(endereco, teto)

    async def corpo() -> None:
        extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal(),  # type: ignore[arg-type]
                                     None, tmp_path, Comunidade(tmp_path, baixar, PUBLICA))
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": JOGO, "memoria": False}))
        assert await asyncio.get_running_loop().run_in_executor(None, entrou.wait, 5)
        await extensao.ao_evento(_evento("perfil.jogo", {"jogo": outro, "memoria": False}))
        liberar.set()
        assert extensao.procurando is not None
        await asyncio.wait_for(extensao.procurando, 5)

    asyncio.run(corpo())
    assert (tmp_path / "comunidade" / f"{JOGO}.json").is_file()
    assert (tmp_path / "comunidade" / f"{outro}.json").is_file()


def test_o_indice_guardado_ilegivel_nao_apaga_a_receita_ja_baixada(tmp_path: Path) -> None:
    repositorio = Repositorio({ARQUIVO: _receita()})
    _comunidade(tmp_path, repositorio).procurar(JOGO, agora=True)
    guardado = tmp_path / "indice-da-comunidade" / "indice.json"
    guardado.write_bytes(guardado.read_bytes().replace(b"golpe-forte", b"golpe-fraco"))
    aqui = Comunidade(tmp_path, _Rede().baixar, PUBLICA)
    assert [aqui.procurar(JOGO)["tipo"], aqui.procurar(JOGO)["tipo"]] == ["erro", "procurado"]
    assert (tmp_path / "comunidade" / f"{JOGO}.json").is_file()
    assert _comunidade(tmp_path, Repositorio({})).procurar(JOGO, agora=True)["achou"] is False
    assert not (tmp_path / "comunidade" / f"{JOGO}.json").exists()
