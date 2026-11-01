"""O formato 1 da receita: as válidas passam, as inválidas recusam com a linha do erro."""
from __future__ import annotations

import json
from typing import Any

import pytest
from apoio import RECEITAS

from motor.efeitos import para_o_trigger_set
from receita.expressao import ExpressaoRecusada, analisar
from receita.formato import TAMANHO_MAXIMO, ReceitaRecusada, ler_receita, receita_vazia


def _recusa(texto: str | bytes) -> ReceitaRecusada:
    with pytest.raises(ReceitaRecusada) as recusa:
        ler_receita(texto)
    return recusa.value


def _base(**mais: Any) -> dict[str, Any]:
    return {"formato": 1, "motor": ">=1,<2", **mais}


def test_a_receita_vazia_e_o_universal() -> None:
    receita = ler_receita((RECEITAS / "universal.json").read_bytes())
    assert receita.universal and receita.ordem == ()
    assert receita_vazia().universal
    assert ler_receita(json.dumps(receita_vazia().dados)).universal


def test_a_receita_completa_passa_e_ordena_os_derivados_antes_dos_estados() -> None:
    receita = ler_receita((RECEITAS / "completa.json").read_bytes())
    assert not receita.universal
    ordem = receita.ordem
    assert ordem.index("tensao") < ordem.index("perigo_total") < ordem.index("perigo")  # (noqa-acento)
    assert ordem.index("vida_baixa") < ordem.index("perigo")


@pytest.mark.parametrize(("arquivo", "linha", "trecho"), [
    ("campo-a-mais.json", 7, "campo desconhecido «taxa_hz»"),
    ("eval-escondido.json", 10, "função fora da lista: «eval»"),
    ("import-escondido.json", 6, "caractere fora da lista: «_»"),
    ("ciclo.json", 10, "ciclo: calma → susto → medo → calma"),
    ("chave-repetida.json", 6, "a chave «tranco» aparece duas vezes"),
    ("formato-novo.json", 2, "mais novo que o deste motor"),
])
def test_a_receita_invalida_recusa_com_a_linha(arquivo: str, linha: int, trecho: str) -> None:
    recusa = _recusa((RECEITAS / arquivo).read_bytes())
    assert recusa.linha == linha, str(recusa)
    assert trecho in str(recusa)
    assert str(recusa).startswith(f"linha {linha}: ")


def test_o_gatilho_fora_da_faixa_do_console_recusa_cada_efeito_na_sua_linha() -> None:
    recusa = _recusa((RECEITAS / "gatilho-fora-da-faixa.json").read_bytes())
    assert [linha for linha, _ in recusa.erros] == [6, 8, 10, 12]
    texto = str(recusa)
    assert "arma_cedo.inicio: 1 fora da faixa de 2 a 7" in texto
    assert "o fim (4) tem de passar do início (6)" in texto
    assert "vibra_sem_frequencia.frequencia: 0 fora da faixa de 1 a 255" in texto
    assert "resiste_sem_forca.forca: 0 fora da faixa de 1 a 8" in texto


def test_65_kb_recusa_antes_de_ler_e_64_kb_passam() -> None:
    corpo = json.dumps(_base(), indent=1)
    cabe = corpo[:-1] + " " * (TAMANHO_MAXIMO - len(corpo)) + "}"
    assert len(cabe.encode()) == TAMANHO_MAXIMO
    assert ler_receita(cabe).universal
    linhas = "\n" * 2000
    passa = corpo[:-1] + linhas + " " * (65 * 1024 - len(corpo) - len(linhas)) + "}"
    recusa = _recusa(passa)
    assert "passa de 64 KB" in str(recusa)
    assert recusa.linha == passa.encode()[:TAMANHO_MAXIMO].count(b"\n") + 1


@pytest.mark.parametrize(("onde", "receita"), [
    ("topo", _base(autor="x")),
    ("jogo", _base(jogo={"chave": "steam_app_1", "loja": "x"})),
    ("builds", _base(jogo={"builds": {"steam_buildid": ["1", "2"], "gog": "3"}})),
    ("entrada", _base(entradas={"f": {"rotulo": "F", "tipo": "ligado", "padrao": True,  # (noqa-acento)
                                      "cor": "#fff"}})),
    ("sentido", _base(permissoes=["ler:botoes"],
                      sentidos={"x": {"de": "botoes", "especie": "evento", "taxa_hz": 1}})),
    ("derivado", _base(derivados={"d": {"expr": "1", "por_ms": 3}})),
    ("estado", _base(estados={"e": {"quando": "1 > 0", "por_ms": 3}})),
    ("efeito", _base(efeitos={"m": {"canal": "motor", "forca": 1, "ritmo": "x"}})),
    ("gatilho", _base(efeitos={"g": {"canal": "gatilho", "modo": "desliga", "lado": "l2",
                                     "forca": 3}})),
    ("regra", _base(efeitos={"m": {"canal": "motor", "forca": 1}},
                    regras=[{"quando": "1", "entao": "m", "mistura": "soma"}])),
    ("confere", _base(permissoes=["ler:botoes"],
                      sentidos={"x": {"de": "botoes", "especie": "evento"}},
                      confere=[{"sentido": "x", "faixa": [0, 1], "muda_em": []}])),
])
def test_o_campo_desconhecido_recusa_em_todo_nivel(onde: str, receita: dict[str, Any]) -> None:
    recusa = _recusa(json.dumps(receita, indent=1))
    assert "campo desconhecido" in str(recusa), (onde, str(recusa))


@pytest.mark.parametrize("texto", [
    "eval('1')", "__import__('os')", "rumble.__class__", "open('/etc/passwd')", "exec(1)",
    "lambda: 1", "rumble ** 2", "'texto'", "rumble[0]", "getattr(rumble, 'x')", "rumble; 1",
    "x if y else z", "1 < 2 < 3", "min(1)", "",
])
def test_a_expressao_fora_da_lista_fechada_recusa(texto: str) -> None:
    with pytest.raises(ExpressaoRecusada):
        analisar(texto)


def test_a_expressao_tem_teto_de_tamanho_e_de_nos() -> None:
    with pytest.raises(ExpressaoRecusada, match="letras"):
        analisar("1+" * 300 + "1")
    with pytest.raises(ExpressaoRecusada, match="nós"):
        analisar("+".join(["1"] * 70))


@pytest.mark.parametrize(("receita", "trecho"), [
    (_base(sentidos={"x": {"de": "botoes", "especie": "evento"}}), "sem declarar «ler:botoes»"),
    (_base(jogo={"leitura_de_memoria": "nunca"}, permissoes=["ler:jogo.memoria"],
           sentidos={"v": {"de": "jogo.memoria", "especie": "nivel",
                           "leitura": {"tipo": "f32", "modulo": "a.exe", "base": "0x10"}}}),  # (noqa-acento)
     "só «pede» lê"),
    (_base(permissoes=["ler:jogo.som"], sentidos={"s": {"de": "jogo.som", "especie": "evento"}},
           efeitos={"m": {"canal": "motor", "forca": 1}},
           regras=[{"quando": "s", "entao": "m", "para": "quem_levou"}]), "quem_levou"),
    (_base(permissoes=["ler:entradas"],
           sentidos={"l2": {"de": "entradas", "especie": "nivel", "campo": "l2"}},
           estados={"aperto": {"quando": "l2 > 0.5 e l2 < 0.9", "histerese": 0.1}}),
     "a histerese só vale"),
    (_base(estados={"est": {"quando": "fantasma > 1"}}), "lê «fantasma»"),
    (_base(estados={"est": {"quando": "1 > $nada"}}), "a entrada «$nada»"),
    (_base(efeitos={"m": {"canal": "motor", "forca": 1}},
           regras=[{"quando": "1", "entao": "sumido"}]), "o efeito «sumido» não existe"),
    (_base(estados={"ou": {"quando": "1"}}), "é palavra das expressões"),
    (_base(motor=">=2"), "não aceita o motor 1"),
    (_base(jogo={"chave": "jogo_qualquer"}), "fora da forma"),
])
def test_a_semantica_recusa_com_a_frase(receita: dict[str, Any], trecho: str) -> None:
    assert trecho in str(_recusa(json.dumps(receita, indent=1)))


def _gatilhos_validos() -> list[dict[str, Any]]:
    base = {"canal": "gatilho", "lado": "r2"}
    return [{**base, **m} for m in (
        {"modo": "desliga"},
        {"modo": "resistencia", "posicao": 0, "forca": 1},  # (noqa-acento)
        {"modo": "resistencia", "posicao": 9, "forca": 8},  # (noqa-acento)
        {"modo": "arma", "inicio": 2, "fim": 3, "forca": 1},
        {"modo": "arma", "inicio": 7, "fim": 8, "forca": 8},
        {"modo": "vibracao", "posicao": 9, "amplitude": 8, "frequencia": 255},  # (noqa-acento)
        {"modo": "vibracao", "posicao": 0, "amplitude": 1, "frequencia": 1},  # (noqa-acento)
        {"modo": "resistencia_por_zona", "forcas": [0, 0, 0, 0, 0, 0, 0, 0, 0, 8]},
        {"modo": "rampa", "inicio": 0, "fim": 1, "forca_inicio": 1, "forca_fim": 8},
        {"modo": "rampa", "inicio": 8, "fim": 9, "forca_inicio": 8, "forca_fim": 1},
        {"modo": "vibracao_por_zona", "frequencia": 1, "amplitudes": [8] + [0] * 9},  # (noqa-acento)
    )]


def test_os_sete_modos_do_gatilho_passam_nas_pontas_da_faixa() -> None:
    efeitos = {f"g{i}": e for i, e in enumerate(_gatilhos_validos())}
    ler_receita(json.dumps(_base(efeitos=efeitos)))


@pytest.mark.parametrize(("mudanca", "trecho"), [
    ({"modo": "arma", "inicio": 8, "fim": 9, "forca": 1}, "fora da faixa de 2 a 7"),
    ({"modo": "arma", "inicio": 2, "fim": 9, "forca": 1}, "fora da faixa de 3 a 8"),
    ({"modo": "resistencia", "posicao": 10, "forca": 1}, "fora da faixa de 0 a 9"),  # (noqa-acento)
    ({"modo": "resistencia_por_zona", "forcas": [9] + [0] * 9}, "fora da faixa de 0 a 8"),
    ({"modo": "resistencia_por_zona", "forcas": [0] * 10}, "use o modo «desliga»"),
    ({"modo": "resistencia_por_zona", "forcas": [1] * 9}, "exatamente 10"),
    ({"modo": "rampa", "inicio": 9, "fim": 9, "forca_inicio": 1, "forca_fim": 1},
     "fora da faixa de 0 a 8"),
    ({"modo": "rampa", "inicio": 5, "fim": 5, "forca_inicio": 1, "forca_fim": 1},
     "tem de passar do início"),
    ({"modo": "vibracao_por_zona", "frequencia": 0, "amplitudes": [1] * 10},  # (noqa-acento)
     "fora da faixa de 1 a 255"),
    ({"modo": "turbo"}, "«modo» pede um de"),
])
def test_o_gatilho_que_o_console_recusaria_recusa(mudanca: dict[str, Any], trecho: str) -> None:
    efeito = {"canal": "gatilho", "lado": "l2", **mudanca}
    assert trecho in str(_recusa(json.dumps(_base(efeitos={"g": efeito}), indent=1)))


def test_cada_gatilho_valido_vira_um_trigger_set_que_o_hefesto_aceita() -> None:
    gatilhos = pytest.importorskip("hefesto_dualsense4unix.core.trigger_effects")
    for efeito in _gatilhos_validos():
        nome, params = para_o_trigger_set(efeito)
        gatilhos.build_from_name(nome, params)
