"""A janela do Modo imersão: cada ajuste das abas muda o que a extensão escreve no controle."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from apoio import DOIS, QUATRO, QUATRO_CONTROLES, RAIZ, TRES, UM, EscritasDeMentira
from test_a_receita_minecraft_dungeons_ii import LINHA_DO_GATILHO, _batimento
from test_a_receita_minecraft_dungeons_ii import _motor as _dungeons
from test_o_cacador import (
    JOGO,
    _achar_a_tela,
    _achar_o_som,
    _evento,
    _PortaDoEstudio,
    _sem_porta,
)
from test_o_universal import (
    _correr,
    _motores,
    _universal,
    entradas,
    microfone,
    na_mao,
    rumble,
    som,
    tela,
)

import opcoes as ajustes
import servidor
from estudio.cacador import Estudio
from motor.laco import HZ, Motor
from motor.saida import Saida
from receita.formato import ler_receita

ABAS = ["Geral", "Controles", "Sentidos", "Efeitos", "Estilos", "Canais", "Receitas"]
TENSO = [(t, microfone(UM, 0.01)) for t in range(0, 20_000, 500)] + na_mao(UM, 20_000)
SUSTO = [*TENSO, (18_000, som("direito", 0.45, 1234.5))]
GOLPE = [(100, entradas(UM, 200)), (200, rumble(UM, 180)), (300, rumble(UM, 0))]
RAJADA = [(t, rumble(TRES, 230)) for t in (1000, 1100, 1200, 1300, 1400)] + [(1500, rumble(TRES, 0))]


def _manifesto() -> dict[str, Any]:
    dado: dict[str, Any] = json.loads((RAIZ / "hefesto-mod.json").read_text(encoding="utf-8"))
    return dado


def _opcoes() -> dict[str, dict[str, Any]]:
    return {o["id"]: o for o in _manifesto()["opcoes"]}  # (noqa-acento)


def _padroes() -> dict[str, Any]:
    return {o["id"]: o["padrao"] for o in _manifesto()["opcoes"] if "padrao" in o}  # (noqa-acento)


def _escrito(opcoes: dict[str, Any], linha: list[Any], ate_ms: int,
             controles: list[dict[str, Any]] | None = None) -> EscritasDeMentira:
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(_universal(controles, opcoes), porta, ate_ms, linha)
    return porta


def _primeiro_estalo(porta: EscritasDeMentira) -> int:
    return next(f for t, f, _ in _motores(porta) if 200 <= t < 400 and f)


def _sustos(porta: EscritasDeMentira) -> tuple[bool, bool]:
    return (bool(porta.de("som.tocar")),
            any(p["id"] == "susto" for _, p in porta.de("haptica.tocar")))  # (noqa-acento)


def _coracoes(porta: EscritasDeMentira) -> list[float]:
    return [t for t, p in porta.de("haptica.tocar")
            if p["id"] == "coracao" and p["forca"] > 0]  # (noqa-acento)


def test_as_abas_seguem_a_ordem_do_desenho_e_o_hefesto_aceita_a_janela() -> None:
    manifesto = _manifesto()
    grupos = ([a["grupo"] for a in manifesto["acoes"]] + [o["grupo"] for o in manifesto["opcoes"]]  # (noqa-acento)
              + [manifesto["aparelhos_acoes"]["grupo"], manifesto["aparelhos_controles"]["grupo"]])
    assert manifesto["abas"] == ABAS
    assert set(grupos) == set(ABAS)
    assert [o["grupo"] for o in manifesto["opcoes"]] == sorted(  # (noqa-acento)
        (o["grupo"] for o in manifesto["opcoes"]), key=ABAS.index)  # (noqa-acento)
    assert manifesto["pagina"]["rotulo"] == "Ensinar este jogo"  # (noqa-acento)
    assert (RAIZ / manifesto["pagina"]["arquivo"]).is_file()  # (noqa-acento)
    assert all(o.get("dica") for o in manifesto["opcoes"])  # (noqa-acento)
    do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.manifesto")
    lido = do_hefesto.ler_manifesto(RAIZ)
    assert [o.id for o in lido.opcoes] == [o["id"] for o in manifesto["opcoes"]]  # (noqa-acento)
    assert [a.id for a in lido.acoes] == [servidor.ACAO_DE_PROCURAR, ajustes.ACAO_DE_VER_A_TELA,
                                          ajustes.ACAO_DE_PARAR_DE_VER, *ajustes.TESTES]


def test_cada_ajuste_da_extensao_e_uma_opcao_da_janela_com_o_mesmo_padrao() -> None:
    opcoes = _opcoes()
    assert opcoes[ajustes.FORCA]["padrao"] == ajustes.FORCA_PADRAO  # (noqa-acento)
    assert opcoes[ajustes.PARA_QUEM]["escolhas"] == list(ajustes.ESCOLHAS_DE_PARA_QUEM)
    assert opcoes[ajustes.PARA_QUEM]["padrao"] == ajustes.QUEM_LEVOU  # (noqa-acento)
    assert ajustes.SENTIDO_DA_TELA not in opcoes
    for ident, (_, padrao) in ajustes.SENTIDOS.items():
        if ident == ajustes.SENTIDO_DA_TELA:
            continue
        assert (opcoes[ident]["grupo"], opcoes[ident]["padrao"]) == ("Sentidos", padrao)  # (noqa-acento)
    for ident in ajustes.CANAIS:
        assert (opcoes[ident]["grupo"], opcoes[ident]["padrao"]) == ("Canais", True)  # (noqa-acento)
    assert opcoes["peso_da_mira"]["grupo"] == "Efeitos"


def test_a_janela_no_padrao_escreve_o_mesmo_que_sem_opcao_nenhuma() -> None:
    padroes = _padroes()
    for linha, ate in ((SUSTO, 19_000), (GOLPE, 600), ([(200, som("esquerdo", 0.4, 0.2))], 600)):
        assert _escrito(padroes, linha, ate).escritas == _escrito({}, linha, ate).escritas


def test_a_forca_pela_metade_escreve_a_metade_e_em_zero_nada_sai() -> None:
    estalo = [(200, som("esquerdo", 0.4, 0.2))]
    assert _primeiro_estalo(_escrito({}, estalo, 600)) == round(0.7 * 255)
    assert _primeiro_estalo(_escrito({ajustes.FORCA: 50}, estalo, 600)) == round(0.35 * 255)
    for linha, ate in ((SUSTO, 19_000), (GOLPE, 600), (estalo, 600)):
        assert _escrito({ajustes.FORCA: 0}, linha, ate).escritas == []


def test_cada_canal_desligado_cala_so_o_que_ele_escreve() -> None:
    assert _sustos(_escrito({"canal_som": False}, SUSTO, 19_000)) == (False, True)
    assert _sustos(_escrito({"canal_haptica": False}, SUSTO, 19_000)) == (True, False)
    assert not _escrito({"canal_gatilho": False}, GOLPE, 600).de("gatilho.set")
    assert _escrito({}, GOLPE, 600).de("gatilho.set")
    estalo = [(200, som("esquerdo", 0.4, 0.2))]
    assert not [m for m in _motores(_escrito({"canal_motor": False}, estalo, 600)) if m[1]]
    assert not _escrito({"canal_leds": False, "lado_na_luz": True}, estalo, 600).de("leds.set")
    assert not _escrito({"canal_luz": False}, RAJADA, 2000, QUATRO_CONTROLES).de("luz.set")


def test_cada_sentido_desligado_para_o_que_vem_dele() -> None:
    estalo = [(200, som("esquerdo", 0.4, 0.2))]
    assert not [m for m in _motores(_escrito({"sentido_som": False}, estalo, 600)) if m[1]]
    assert not _escrito({"sentido_vibracao": False}, RAJADA, 2000, QUATRO_CONTROLES).de("luz.set")
    assert not _coracoes(_escrito({"sentido_microfone": False}, TENSO, 20_000))
    assert not _escrito({"sentido_golpe": False}, GOLPE, 600).de("gatilho.set")
    dano = [(1000, tela(0.8, 1.0))]
    assert not _escrito({}, dano, 1500).de("luz.set")
    assert _escrito({"sentido_tela": True}, dano, 1500).de("luz.set")


def test_cada_efeito_da_aba_efeitos_muda_o_que_sai() -> None:
    estalo = [(200, som("esquerdo", 0.4, 0.2))]
    assert _primeiro_estalo(_escrito({"golpe_com_lado": 40}, estalo, 600)) == round(0.4 * 255)
    assert _sustos(_escrito({"susto_no_alto_falante": False}, SUSTO, 19_000)) == (False, True)
    assert _sustos(_escrito({"susto_no_tato": False}, SUSTO, 19_000)) == (True, False)
    assert not _escrito({"impacto_nos_gatilhos": False}, GOLPE, 600).de("gatilho.set")
    assert not _escrito({"luz_do_dano": False}, RAJADA, 2000, QUATRO_CONTROLES).de("luz.set")
    assert not _coracoes(_escrito({"coracao": 0}, TENSO, 20_000))  # (noqa-acento)
    forte, fraco = (max(p["forca"] for t, p in _escrito({"coracao": c}, TENSO, 20_000).de(  # (noqa-acento)
        "haptica.tocar") if p["id"] == "coracao") for c in (100, 50))  # (noqa-acento)
    assert fraco == pytest.approx(forte / 2, rel=0.05)


def test_o_clima_tenso_mais_baixo_liga_o_coracao_mais_cedo() -> None:
    cedo, padrao = (_coracoes(_escrito({"clima": c}, TENSO, 20_000)) for c in (10, 35))
    assert cedo and padrao and cedo[0] < padrao[0]
    assert not _coracoes(_escrito({"clima": 90}, TENSO, 20_000))


def test_o_golpe_vai_para_todos_os_controles_quando_a_janela_pede() -> None:
    so_quem, todos = (_escrito({ajustes.PARA_QUEM: p}, RAJADA, 2000, QUATRO_CONTROLES)
                      for p in ajustes.ESCOLHAS_DE_PARA_QUEM)
    assert {p["uniq"] for _, p in so_quem.de("luz.set")} == {TRES}
    assert {p["uniq"] for _, p in todos.de("luz.set")} == {UM, DOIS, TRES, QUATRO}


class _Porta:
    def __init__(self) -> None:
        self.pedidos: list[tuple[str, dict[str, Any]]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {}


def test_o_botao_procurar_receitas_da_aba_geral_procura_na_hora() -> None:
    extensao = servidor.Extensao(_Porta(), servidor.carregar_o_universal())  # type: ignore[arg-type]
    pedidos: list[bool] = []
    extensao.procurar_em_fundo = lambda agora=False: pedidos.append(agora)  # type: ignore[method-assign]

    async def corpo() -> None:
        for acao in ("outra", servidor.ACAO_DE_PROCURAR):
            await extensao.ao_evento({"method": "evento", "params": {
                "topico": "extensao.acao", "nome": "extensao.acao", "uniq": None,
                "dados": {"mod": "modo-imersao", "acao": acao, "alvo": None}}})  # (noqa-acento)

    asyncio.run(corpo())
    assert pedidos == [True]


RECEITAS_DE_FABRICA = [RAIZ / "receitas" / "universal.json",
                       *sorted((RAIZ / "receitas" / "estudadas").glob("*.json"))]
SO_NO_UNIVERSAL = {"alivio", "peso_da_mira"}


@pytest.mark.parametrize("arquivo", RECEITAS_DE_FABRICA, ids=lambda a: a.stem)
def test_toda_receita_de_fabrica_le_as_abas_efeitos_e_susto_com_o_padrao_da_janela(
        arquivo: Any) -> None:
    efeitos = {i: o for i, o in _opcoes().items()
               if o["grupo"] == "Efeitos" and not i.startswith("tipo_")}
    declaradas = ler_receita(arquivo.read_bytes()).secao("entradas")
    fora = {"peso_da_mira"} if arquivo.stem == "universal" else SO_NO_UNIVERSAL
    pedidas = set(efeitos) - fora
    assert pedidas <= set(declaradas)
    for ident in set(efeitos) & set(declaradas):
        entrada, opcao = declaradas[ident], efeitos[ident]
        assert (entrada["tipo"], entrada["padrao"]) == (opcao["tipo"], opcao["padrao"])  # (noqa-acento)
        assert (entrada.get("minimo"), entrada.get("maximo")) == (  # (noqa-acento)
            opcao.get("minimo"), opcao.get("maximo"))  # (noqa-acento)


def _no_dungeons(opcoes: dict[str, Any], linha: list[Any], ate_ms: int) -> EscritasDeMentira:
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(_dungeons(opcoes), porta, ate_ms, linha)
    return porta


def test_no_dungeons_a_janela_no_padrao_escreve_o_mesmo_e_cada_efeito_muda_o_que_sai() -> None:
    padroes = _padroes()
    susto = _batimento(0, 9000) + [(7000, som("direito", 0.45, 70.0))]
    estalo = [(200, som("esquerdo", 0.4, 0.2))]
    for linha, ate in ((susto, 9000), (LINHA_DO_GATILHO, 5000), (estalo, 600)):
        assert _no_dungeons(padroes, linha, ate).escritas == _no_dungeons({}, linha, ate).escritas
    assert _sustos(_no_dungeons({"susto_no_alto_falante": False}, susto, 9000)) == (False, True)
    assert _sustos(_no_dungeons({"susto_no_tato": False}, susto, 9000)) == (True, False)
    assert not _coracoes(_no_dungeons({"coracao": 0}, susto, 9000))  # (noqa-acento)
    acelerados = [(c, {p["forca"] for _, p in _no_dungeons({"clima": c}, susto, 9000).de(  # (noqa-acento)
        "haptica.tocar") if p["id"] == "coracao"}) for c in (35, 90)]  # (noqa-acento)
    assert [(c, 0.75 in forcas) for c, forcas in acelerados] == [(35, True), (90, False)]
    assert _primeiro_estalo(_no_dungeons({"golpe_com_lado": 35}, estalo, 600)) == round(0.3 * 255)
    impactos = [p for _, p in _no_dungeons({"impacto_nos_gatilhos": False}, LINHA_DO_GATILHO,
                                           5000).de("gatilho.set") if p["modo"] != "Off"]
    assert not impactos
    rajada = [(t, rumble(UM, 230)) for t in (1000, 1100, 1200, 1300, 1400)] + [(1500, rumble(UM, 0))]
    assert _no_dungeons({}, rajada, 2000).de("luz.set")
    assert not _no_dungeons({"luz_do_dano": False}, rajada, 2000).de("luz.set")


ESTALO_CRU = json.dumps({
    "formato": 1, "motor": ">=1,<2", "permissoes": ["ler:jogo.som"],  # (noqa-acento)
    "sentidos": {"estalo": {"de": "jogo.som", "especie": "evento", "nome": "jogo.som"}},
    "efeitos": {"tranco": {"canal": "motor", "lado": "ambos", "forca": 0.5, "dura_ms": 100}},
    "regras": [{"quando": "estalo", "entao": "tranco", "para": "todos"}]})


def test_o_sentido_desligado_cala_tambem_a_receita_que_le_o_topico_cru() -> None:
    estalo = [(200, som("esquerdo", 0.4, 0.2))]
    feitos = []
    for opcoes in ({}, {"sentido_som": False}):
        motor = Motor(ler_receita(ESTALO_CRU), opcoes)
        motor.controles([{"uniq": UM, "jogador": 1}])
        porta = EscritasDeMentira()
        _correr(motor, porta, 600, estalo)
        feitos.append(bool([m for m in _motores(porta) if m[1]]))
    assert feitos == [True, False]


def _ensinar_pela_tela(dados: Path, porta: _PortaDoEstudio) -> servidor.Extensao:
    async def corpo() -> servidor.Extensao:
        biblioteca = servidor.Biblioteca(servidor.PASTA_DAS_ESTUDADAS, dados,
                                         servidor.carregar_o_universal, servidor.diario)
        extensao = servidor.Extensao(porta, biblioteca.para(None, servidor.PELO_JOGO),  # type: ignore[arg-type]
                                     biblioteca, dados)
        await extensao.assinar()
        await extensao.ao_evento(_evento("perfil.jogo", "perfil.trocou",
                                         {"jogo": JOGO, "memoria": False}))
        await extensao.ao_evento(_evento("extensao.mensagem", "extensao.mensagem",
                                         {"id": 1, "dados": {"tipo": "comecar",
                                                             "cacador": "tela"}}))
        for _ in range(3):
            await extensao.ao_evento(_evento("botoes", "button.down",
                                             {"button": "ps", "botao": "ps", "pressed": True,
                                              "uniq": UM, "jogador": 1}, UM))
        await extensao.ao_evento(_evento("extensao.mensagem", "extensao.mensagem",
                                         {"id": 2, "dados": {"tipo": "guardar",
                                                             "nome": "Barra"}}))
        return extensao

    return asyncio.run(corpo())


def _assinados_pela_porta(porta: _PortaDoEstudio) -> set[str]:
    vivos: set[str] = set()
    for metodo, params in porta.pedidos:
        if metodo == "eventos.assinar":
            vivos |= set(params["topicos"])
        elif metodo == "eventos.desassinar":
            vivos -= set(params["topicos"])
    return vivos


def test_a_receita_ensinada_pela_tela_nao_liga_a_tela_sem_o_clique(tmp_path: Path) -> None:
    (tmp_path / "opcoes.json").write_text(json.dumps({"forca_geral": 70}), encoding="utf-8")
    porta = _PortaDoEstudio()
    extensao = _ensinar_pela_tela(tmp_path, porta)
    assert extensao.escolhida.origem == "sua"
    guardadas = json.loads((tmp_path / "opcoes.json").read_text(encoding="utf-8"))
    assert guardadas == {"forca_geral": 70}
    assert extensao.opcoes.get("sentido_tela") is False
    assert "jogo.tela" not in extensao.assinados
    assert "jogo.tela" not in _assinados_pela_porta(porta)


def test_o_achado_da_tela_guardado_nao_liga_a_tela(tmp_path: Path) -> None:
    desligados = {"sentido_som": False, "sentido_golpe": False}
    (tmp_path / "opcoes.json").write_text(json.dumps(desligados), encoding="utf-8")
    achado = _achar_a_tela()
    assert achado is not None
    estudio = Estudio(_sem_porta, tmp_path / "receitas", ler_receita)
    estudio.jogo, estudio.cacador, estudio.achado = JOGO, "tela", achado
    resposta = asyncio.run(estudio.mensagem({"tipo": "guardar", "nome": "Achado"}, 0.0))
    assert resposta["tipo"] == "guardado"
    guardadas = json.loads((tmp_path / "opcoes.json").read_text(encoding="utf-8"))
    assert guardadas == desligados
    assert not ajustes.topico_ligado("jogo.tela", guardadas)


@pytest.mark.parametrize(("tipo", "topico", "sentido"), [("som", "jogo.som", "sentido_som")])
def test_o_achado_guardado_liga_o_sentido_que_ele_le_e_nao_mexe_em_outro(
        tmp_path: Path, tipo: str, topico: str, sentido: str) -> None:
    desligados = {"sentido_som": False, "sentido_golpe": False}
    (tmp_path / "opcoes.json").write_text(json.dumps(desligados), encoding="utf-8")
    achado = _achar_o_som() if tipo == "som" else _achar_a_tela()
    assert achado is not None
    estudio = Estudio(_sem_porta, tmp_path / "receitas", ler_receita)
    estudio.jogo, estudio.cacador, estudio.achado = JOGO, tipo, achado
    resposta = asyncio.run(estudio.mensagem({"tipo": "guardar", "nome": "Achado"}, 0.0))
    assert resposta["tipo"] == "guardado"
    guardadas = json.loads((tmp_path / "opcoes.json").read_text(encoding="utf-8"))
    assert guardadas == {**desligados, sentido: True}
    assert ajustes.topico_ligado(topico, guardadas)


def test_o_achado_recusado_nao_liga_sentido_nenhum(tmp_path: Path) -> None:
    achado = _achar_a_tela()
    assert achado is not None
    estudio = Estudio(_sem_porta, tmp_path / "receitas", ler_receita)
    estudio.jogo, estudio.cacador, estudio.achado = JOGO, "tela", achado
    resposta = asyncio.run(estudio.mensagem({"tipo": "guardar", "nome": ""}, 0.0))
    assert resposta["tipo"] == "erro"
    assert not (tmp_path / "opcoes.json").exists()


SUSTOS = [*TENSO, *((t, som("direito", 0.45, 1234.5)) for t in (12_000, 14_000, 18_000))]
SUSTOS_NO_DUNGEONS = [*_batimento(0, 15_000),
                      *((t, som("direito", 0.45, 70.0)) for t in (7000, 9000, 13_000))]
VERMELHO, VERDE = [255, 0, 0], [0, 255, 0]


def _da_receita(texto: str, opcoes: dict[str, Any], linha: list[Any], ate_ms: int,
                controles: list[dict[str, Any]]) -> EscritasDeMentira:
    motor = Motor(ler_receita(texto), opcoes)
    motor.controles(controles)
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(motor, porta, ate_ms, linha)
    return porta


def _linhas(arquivo: Path) -> list[tuple[list[Any], int, list[dict[str, Any]]]]:
    sustos = SUSTOS if arquivo.stem == "universal" else SUSTOS_NO_DUNGEONS
    return [(RAJADA, 2000, QUATRO_CONTROLES), (sustos, 19_000, [{"uniq": UM, "jogador": 1}])]


@pytest.mark.parametrize("arquivo", RECEITAS_DE_FABRICA, ids=lambda a: a.stem)
def test_a_cor_do_dano_e_o_intervalo_do_susto_no_padrao_escrevem_o_mesmo_que_os_valores_fixos(
        arquivo: Path) -> None:
    texto = arquivo.read_text(encoding="utf-8")
    assert '"cor": "$cor_do_dano"' in texto and '"espera_ms": "$intervalo_do_susto * 1000"' in texto
    fixa = texto.replace('"$cor_do_dano"', '"#ff0000"').replace(
        '"$intervalo_do_susto * 1000"', "5000")
    padroes = _padroes()
    for linha, ate, controles in _linhas(arquivo):
        antes = _da_receita(fixa, {}, linha, ate, controles)
        assert antes.de("luz.set") or antes.de("som.tocar")
        for opcoes in ({}, padroes):
            assert _da_receita(texto, opcoes, linha, ate, controles).escritas == antes.escritas


@pytest.mark.parametrize("arquivo", RECEITAS_DE_FABRICA, ids=lambda a: a.stem)
def test_a_cor_do_dano_e_o_intervalo_do_susto_mudam_o_que_sai(arquivo: Path) -> None:
    texto = arquivo.read_text(encoding="utf-8")
    rajada, sustos = _linhas(arquivo)

    def cores(opcoes: dict[str, Any]) -> list[list[int]]:
        return [p["rgb"] for _, p in _da_receita(texto, opcoes, *rajada).de("luz.set")]

    def tocados(opcoes: dict[str, Any]) -> int:
        return len(_da_receita(texto, opcoes, *sustos).de("som.tocar"))

    assert cores({}) and {tuple(c) for c in cores({})} == {tuple(VERMELHO)}
    assert {tuple(c) for c in cores({"cor_do_dano": "#00ff00"})} == {tuple(VERDE)}
    assert {tuple(c) for c in cores({"cor_do_dano": "verde"})} == {tuple(VERMELHO)}
    assert (tocados({"intervalo_do_susto": 1}), tocados({}),
            tocados({"intervalo_do_susto": 10})) == (3, 2, 1)


@pytest.mark.parametrize(("onde", "valor", "frase"), [
    (("efeitos", "vermelho", "cor"), "$clima", "não é uma entrada de cor"),
    (("efeitos", "vermelho", "cor"), "vermelho", "pede uma cor"),
    (("regras", 7, "espera_ms"), "$cor_do_dano * 1000", "é uma cor e não entra em conta"),
    (("regras", 7, "espera_ms"), "$sem_entrada * 1000", "que não existe"),
    (("entradas", "cor_do_dano", "padrao"), "vermelho", "padrão #rrggbb"),  # (noqa-acento)
], ids=["cor-que-nao-e-cor", "cor-fora-da-forma", "cor-na-conta", "entrada-que-falta",
        "padrao-da-cor-fora-da-forma"])
def test_a_receita_recusa_a_cor_e_o_intervalo_fora_da_forma(onde: tuple[Any, ...], valor: Any,
                                                             frase: str) -> None:
    bruto = json.loads((RAIZ / "receitas" / "universal.json").read_text(encoding="utf-8"))
    alvo = bruto
    for parte in onde[:-1]:
        alvo = alvo[parte]
    alvo[onde[-1]] = valor
    with pytest.raises(servidor.ReceitaRecusada, match=frase):
        ler_receita(json.dumps(bruto))


def test_a_cor_mora_nos_efeitos_e_o_intervalo_no_susto_com_o_padrao_de_antes() -> None:
    opcoes = _opcoes()
    cor, intervalo = opcoes["cor_do_dano"], opcoes["intervalo_do_susto"]
    assert (cor["tipo"], cor["padrao"], cor["grupo"]) == ("cor", "#ff0000", "Efeitos")  # (noqa-acento)
    assert cor["aparece_com"] == {"luz_do_dano": True, "@presente": "cor_do_dano"}
    assert (intervalo["padrao"], intervalo["unidade"], intervalo["grupo"]) == (5, "s", "Efeitos")  # (noqa-acento)
    assert (cor["cartao"], intervalo["cartao"]) == ("Luz do dano", "Susto")


class _PortaDosControles(_Porta):
    def __init__(self, controles: list[dict[str, Any]]) -> None:
        super().__init__()
        self.controles = controles

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        self.pedidos.append((metodo, params))
        return {"controles": self.controles} if metodo == "controles.lista" else {}

    def estados(self) -> list[dict[str, Any]]:
        return [p for m, p in self.pedidos if m == "acessorios.estado"]


TRES_CONECTADOS: list[dict[str, Any]] = [
    {"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}, {"uniq": TRES, "jogador": None}]


def _ligar(alvo: str, valor: bool) -> dict[str, Any]:
    return {"method": "evento", "params": {
        "topico": "extensao.acao", "nome": "extensao.acao", "uniq": None,
        "dados": {"mod": "imersao", "acao": "ligar", "alvo": alvo, "valor": valor}}}  # (noqa-acento)


def _com_os_controles(dados: Path, *eventos: dict[str, Any]
                      ) -> tuple[servidor.Extensao, _PortaDosControles]:
    porta = _PortaDosControles(TRES_CONECTADOS)
    extensao = servidor.Extensao(porta, servidor.carregar_o_universal(), dados=dados)  # type: ignore[arg-type]

    async def corpo() -> None:
        await extensao.atualizar_os_controles()
        await extensao.publicar_o_estado()
        for evento in eventos:
            await extensao.ao_evento(evento)

    asyncio.run(corpo())
    return extensao, porta


def test_cada_controle_conectado_e_um_cartao_da_aba_controles_com_a_chave_e_sem_o_uniq(
        tmp_path: Path) -> None:
    manifesto = _manifesto()
    assert manifesto["aparelhos_acoes"] == {"grupo": "Controles", "acoes": [  # (noqa-acento)
        {"id": "ligar", "rotulo": "Sente os efeitos", "icone": "ligar"}]}
    extensao, porta = _com_os_controles(tmp_path)
    assert [{k: v for k, v in a.items() if k != "controles"}
            for a in porta.estados()[-1]["aparelhos"]] == [
        {"id": "jogador-1", "nome": "Jogador 1", "ligado": True},
        {"id": "jogador-2", "nome": "Jogador 2", "ligado": True},
        {"id": "controle-3", "nome": "Jogador 3", "ligado": True}]
    assert not any(u in json.dumps(porta.estados()) for u in (UM, DOIS, TRES))
    assert extensao.motor.calados == frozenset()
    porta_do_hefesto = pytest.importorskip("hefesto_dualsense4unix.mods.porta")
    aceito = porta_do_hefesto.estado_dos_acessorios(
        "imersao", porta.estados()[-1], acoes_dos_aparelhos=frozenset({"ligar"}))
    assert [a["id"] for a in aceito["aparelhos"]] == ["jogador-1", "jogador-2", "controle-3"]


def test_o_controle_desligado_na_janela_nao_recebe_nada_e_a_escolha_sobrevive_ao_reinicio(
        tmp_path: Path) -> None:
    extensao, porta = _com_os_controles(tmp_path, _ligar("jogador-2", False))
    assert extensao.motor.calados == {DOIS}
    assert [a["ligado"] for a in porta.estados()[-1]["aparelhos"]] == [True, False, True]
    assert json.loads((tmp_path / "controles.json").read_text(encoding="utf-8")) == {
        "calados": ["jogador-2"]}
    assert (tmp_path / "controles.json").stat().st_mode & 0o777 == 0o600

    renascida, _ = _com_os_controles(tmp_path)
    assert renascida.motor.calados == {DOIS}

    devolvida, porta = _com_os_controles(tmp_path, _ligar("jogador-2", True),
                                         _ligar(UM, False))
    assert devolvida.motor.calados == frozenset()
    assert [a["ligado"] for a in porta.estados()[-1]["aparelhos"]] == [True, True, True]


def test_o_motor_nao_escreve_no_controle_calado_e_segue_nos_outros() -> None:
    for calados, sentem in (({DOIS}, {UM, TRES, QUATRO}), (set(), {UM, DOIS, TRES, QUATRO})):
        motor = _universal(QUATRO_CONTROLES, {ajustes.PARA_QUEM: ajustes.TODOS})
        motor.calar(calados)
        porta = EscritasDeMentira(com_haptica=True, com_som=True)
        _correr(motor, porta, 2000, RAJADA)
        assert {p["uniq"] for _, p in porta.de("luz.set")} == sentem
        assert not [e for e in porta.escritas if e[2].get("uniq") in calados]
    sozinho = _universal(None, {})
    sozinho.calar({UM})
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    _correr(sozinho, porta, 19_000, [*GOLPE, *SUSTO])
    assert porta.escritas == []


def test_o_clima_da_cena_vai_ao_nivel_do_agora_e_so_se_republica_quando_muda(
        tmp_path: Path) -> None:
    assert {"nivel", "clima"} <= set(_manifesto()["agora"])
    climas = []
    for ate in (0, 10_000, 20_000):
        motor = _universal(None, {})
        _correr(motor, EscritasDeMentira(com_haptica=True, com_som=True), ate, TENSO)
        climas.append(motor.clima())
    assert climas[0] == 0 and climas[-1] >= 3

    extensao, janela = _com_os_controles(tmp_path)
    assert janela.estados()[-1]["nivel"] == 0
    extensao.motor.valores["tensao"] = 0.62  # (noqa-acento)
    asyncio.run(extensao.publicar_se_mudou())
    asyncio.run(extensao.publicar_se_mudou())
    assert [e["nivel"] for e in janela.estados()] == [0, 6]
    assert {e["limiar"] for e in janela.estados()} == {round(_padroes()["clima"] / 10)}


def test_o_controle_calado_no_meio_do_efeito_solta_o_que_tinha_e_nao_recebe_mais_nada() -> None:
    motor = _universal([{"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}],
                       {ajustes.PARA_QUEM: ajustes.TODOS})
    porta = EscritasDeMentira(com_haptica=True, com_som=True)
    fila = sorted(TENSO, key=lambda e: e[0])
    cala_ms = 15_000

    async def correr() -> None:
        k = 0
        saida = Saida(porta.pedir)
        while (t := k * 1000 / HZ) <= 20_000:
            if t >= cala_ms and not motor.calados:
                motor.calar({DOIS})
            while fila and fila[0][0] <= t + 1e-6:
                motor.evento(*fila.pop(0)[1])
            porta.agora = t
            await saida.aplicar(t, motor.passo(t))
            k += 1

    asyncio.run(correr())
    antes = [p for t, _, p in porta.escritas if p.get("uniq") == DOIS and t < cala_ms]
    depois = [p for t, _, p in porta.escritas if p.get("uniq") == DOIS and t >= cala_ms]
    assert any(p.get("forca") for p in antes)
    assert depois and all(p.get("forca") == 0.0 and p.get("ate_ms") == 0 for p in depois)
    assert len(depois) == len({p["lado"] for p in depois})
    assert [t for t, _, p in porta.escritas if p.get("uniq") == UM and t >= cala_ms]


def test_cada_efeito_e_um_cartao_com_o_tipo_dele_e_a_janela_pede_o_controle_vivo() -> None:
    manifesto = _manifesto()
    opcoes = _opcoes()
    assert manifesto["agora"] == ["controle", "nivel", "clima", "perfil", "linhas", "ao_vivo"]
    cartoes: dict[str, list[str]] = {}
    for o in manifesto["opcoes"]:  # (noqa-acento)
        if "cartao" in o:
            assert o["grupo"] == "Efeitos"
            cartoes.setdefault(o["cartao"], []).append(o["id"])
    assert cartoes["Coração"] == ["coracao", "tipo_do_coracao"]
    assert cartoes["Impacto nos gatilhos"] == ["impacto_nos_gatilhos", "tipo_do_l2", "tipo_do_r2"]
    assert cartoes["Susto"][:2] == ["susto_no_alto_falante", "susto_no_tato"]
    assert opcoes["coracao"]["rotulo"] == opcoes["coracao"]["cartao"] == "Coração"
    assert {opcoes[i]["canal"] for i in ("canal_haptica", "canal_motor", "canal_gatilho",
                                          "canal_luz", "canal_leds", "canal_som")} == {
        "haptica", "vibracao", "gatilho", "luz", "leds", "som"}
    assert {a["grupo"] for a in manifesto["acoes"] if a["id"].startswith("testar_")} == {"Efeitos"}
