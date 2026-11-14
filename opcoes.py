"""Os ajustes que são da extensão, não da receita: a Força, para quem vai o golpe, os sentidos e
os canais, e os controles que sentem. A tela não tem chave: ela só se lê depois do clique «Ver a
tela», e o estado do clique entra nas opções por :func:`com_a_tela`. Valem para toda receita (a sua, a estudada, a da comunidade e o universal), no tique
seguinte, lidos do mesmo ``opcoes.json`` que a janela grava."""
from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

ARQUIVO_DAS_OPCOES = "opcoes.json"
ARQUIVO_DOS_CONTROLES = "controles.json"
ACAO_DE_LIGAR = "ligar"
ACAO_DE_VER_A_TELA = "ver_a_tela"
ACAO_DE_PARAR_DE_VER = "parar_de_ver"
SENTIDO_DA_TELA = "sentido_tela"
TESTES: dict[str, tuple[str, ...]] = {
    "testar_coracao": ("tipo_do_coracao",),
    "testar_alivio": ("tipo_do_alivio",),
    "testar_golpe": ("tipo_do_golpe",),
    "testar_susto": ("tipo_do_susto",),
    "testar_gatilhos": ("tipo_do_l2", "tipo_do_r2"),
}
TOPICO_DA_TELA = "jogo.tela"
ID_DO_CONTROLE = re.compile(r"^(?:jogador|controle)-[1-9][0-9]?$")
FORCA = "forca_geral"
FORCA_PADRAO = 100.0
PARA_QUEM = "para_quem"
QUEM_LEVOU = "Quem levou"
TODOS = "Todos os controles"
ESCOLHAS_DE_PARA_QUEM = (QUEM_LEVOU, TODOS)
CONTROLE_DA_FORCA = "forca"
CONTROLE_DO_VOLUME = "volume"
NIVEIS_DO_CONTROLE = (0, 25, 50, 75, 100)
NIVEL_PADRAO = 100
CONTROLES_DO_CARTAO = (
    (CONTROLE_DA_FORCA, "Força", "A força de tudo o que este controle sente, vezes a Força geral"),
    (CONTROLE_DO_VOLUME, "Volume", "O volume do alto-falante deste controle; não mexe na Força"),
)

SENTIDOS: dict[str, tuple[tuple[str, ...], bool]] = {
    "sentido_som": (("sentido.som", "jogo.som"), True),
    "sentido_vibracao": (("sentido.rumble",), True),
    "sentido_microfone": (("sentido.microfone", "microfone.nivel"), True),
    "sentido_parado": (("sentido.quietude",), True),
    "sentido_tela": (("sentido.tela", "jogo.tela"), False),
    "sentido_golpe": (("sentido.golpe",), True),
}

CANAIS: dict[str, str] = {
    "canal_haptica": "haptica",
    "canal_motor": "motor",
    "canal_gatilho": "gatilho",
    "canal_luz": "luz",
    "canal_leds": "leds",
    "canal_som": "som",
}

TOPICOS_DA_PORTA_COM_CHAVE: dict[str, tuple[str, bool]] = {
    topico: (ident, padrao)
    for ident, (topicos, padrao) in SENTIDOS.items()
    for topico in topicos if not topico.startswith("sentido.")
}


def com_a_tela(opcoes: dict[str, Any], vendo: bool) -> dict[str, Any]:
    """As opções com o sentido da tela no estado do clique «Ver a tela»: o arquivo nunca o liga."""
    return {**{k: v for k, v in opcoes.items() if k != SENTIDO_DA_TELA}, SENTIDO_DA_TELA: vendo}


def migrar(dados: Path) -> bool:
    """O ``opcoes.json`` de antes da 0.5.0 guardava a chave da tela: ela sai, e a tela fica
    desligada até o clique. ``True`` quando o arquivo mudou."""
    arquivo = dados / ARQUIVO_DAS_OPCOES
    valores = _ler(arquivo)
    if SENTIDO_DA_TELA not in valores:
        return False
    del valores[SENTIDO_DA_TELA]
    _gravar(dados, ARQUIVO_DAS_OPCOES, valores)
    return True


def ligado(opcoes: dict[str, Any], ident: str, padrao: bool = True) -> bool:
    valor = opcoes.get(ident, padrao)
    return valor if isinstance(valor, bool) else padrao


def forca(opcoes: dict[str, Any]) -> float:
    """A Força, de 0 a 1: multiplica tudo o que a extensão escreve; em 0, nada sai."""
    valor = opcoes.get(FORCA, FORCA_PADRAO)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        valor = FORCA_PADRAO
    return min(1.0, max(0.0, float(valor) / 100.0))


def para_todos(opcoes: dict[str, Any]) -> bool:
    return opcoes.get(PARA_QUEM) == TODOS


def topicos_calados(opcoes: dict[str, Any]) -> frozenset[str]:
    """Os tópicos dos sentidos que a janela desligou: o que vem deles não chega à receita."""
    return frozenset(t for ident, (topicos, padrao) in SENTIDOS.items()
                     if not ligado(opcoes, ident, padrao) for t in topicos)


def canais_calados(opcoes: dict[str, Any]) -> frozenset[str]:
    return frozenset(canal for ident, canal in CANAIS.items() if not ligado(opcoes, ident))


def topico_ligado(topico: str, opcoes: dict[str, Any] | None = None) -> bool:
    """O tópico da porta que só se assina com o sentido dele ligado."""
    ident, padrao = TOPICOS_DA_PORTA_COM_CHAVE.get(topico, ("", True))
    return ligado(opcoes or {}, ident, padrao) if ident else True


def consentir(dados: Path, topico: str) -> bool:
    """Ensinar a receita pelo tópico é o gesto que o consente: o sentido dele passa a ligado no
    ``opcoes.json`` (arquivo novo e ``rename``, em ``0600``, as outras opções intactas).
    ``True`` quando a chave mudou; desligá-la depois volta a calar a receita."""
    ident, padrao = TOPICOS_DA_PORTA_COM_CHAVE.get(topico, ("", True))
    if not ident or ident == SENTIDO_DA_TELA:
        return False
    valores = _ler(dados / ARQUIVO_DAS_OPCOES)
    if ligado(valores, ident, padrao):
        return False
    valores[ident] = True
    _gravar(dados, ARQUIVO_DAS_OPCOES, valores)
    return True


def id_do_controle(jogador: Any, posicao: int) -> str:
    """O ``id`` do controle na janela: o número do jogador, ou a posição na lista sem ele. Nunca
    o ``uniq``, que diria qual controle é."""
    if isinstance(jogador, int) and not isinstance(jogador, bool) and jogador >= 1:
        return f"jogador-{jogador}"
    return f"controle-{posicao}"


def nome_do_controle(controle: dict[str, Any], posicao: int) -> str:
    """A cor do plástico quando a porta a diz; sem ela, o jogador."""
    cor = controle.get("cor")
    if isinstance(cor, str) and cor.strip():
        return cor.strip()[:60]
    jogador = controle.get("jogador")
    numero = jogador if isinstance(jogador, int) and not isinstance(jogador, bool) else posicao
    return f"Jogador {numero}"


def controles_calados(dados: Path | None) -> frozenset[str]:
    """Os controles que a janela desmarcou, pelo ``id``; um controle nasce sentindo."""
    if dados is None:
        return frozenset()
    calados = _ler(dados / ARQUIVO_DOS_CONTROLES).get("calados")
    return frozenset(c for c in calados if isinstance(c, str) and ID_DO_CONTROLE.match(c)
                     ) if isinstance(calados, list) else frozenset()


def niveis_dos_controles(dados: Path | None) -> dict[str, dict[str, int]]:
    """A Força e o volume de cada controle, ``{controle: {id: nível}}``, pelo ``id`` do cartão;
    o que falta ou está fora dos níveis vale 100."""
    if dados is None:
        return {}
    lidos = _ler(dados / ARQUIVO_DOS_CONTROLES)
    niveis: dict[str, dict[str, int]] = {}
    for controle, _rotulo, _dica in CONTROLES_DO_CARTAO:
        bruto = lidos.get(controle)
        niveis[controle] = {ident: valor for ident, valor in (
            bruto.items() if isinstance(bruto, dict) else ())
            if isinstance(ident, str) and ID_DO_CONTROLE.match(ident)
            and valor in NIVEIS_DO_CONTROLE and not isinstance(valor, bool)}
    return niveis


def nivel(niveis: dict[str, dict[str, int]], controle: str, ident: str) -> int:
    return niveis.get(controle, {}).get(ident, NIVEL_PADRAO)


def ajustar_o_nivel(niveis: dict[str, dict[str, int]], controle: str, ident: str,
                    valor: Any) -> dict[str, dict[str, int]]:
    """O clique num nível do cartão: ``valor`` é o ``id`` do botão (``"0"`` a ``"100"``); fora
    dos níveis ou de um controle conhecido, nada muda."""
    if (controle not in dict.fromkeys(c for c, _, _ in CONTROLES_DO_CARTAO)
            or not ID_DO_CONTROLE.match(ident) or not isinstance(valor, str)
            or not valor.isdigit() or int(valor) not in NIVEIS_DO_CONTROLE):
        return niveis
    novos = {c: dict(v) for c, v in niveis.items()}
    novos.setdefault(controle, {})[ident] = int(valor)
    return novos


def controles_do_cartao(niveis: dict[str, dict[str, int]], ident: str) -> list[dict[str, Any]]:
    """Os dois controles do cartão, lado a lado: a Força e o volume, em níveis de 25 %."""
    return [{"id": controle, "tipo": "escolha", "rotulo": rotulo, "dica": dica,
             "valor": str(nivel(niveis, controle, ident)),
             "opcoes": [{"id": str(n), "rotulo": f"{n}%"} for n in NIVEIS_DO_CONTROLE]}
            for controle, rotulo, dica in CONTROLES_DO_CARTAO]


def sentir(calados: frozenset[str], ident: str, sente: bool) -> frozenset[str]:
    """A chave do controle na janela: ``sente`` falso o cala, verdadeiro o devolve."""
    if not ID_DO_CONTROLE.match(ident):
        return calados
    return calados - {ident} if sente else calados | {ident}


def guardar_os_controles(dados: Path, calados: frozenset[str],
                         niveis: dict[str, dict[str, int]] | None = None) -> None:
    """No ``controles.json``, à parte do ``opcoes.json``, que o Hefesto reescreve só com as
    opções declaradas: os calados e, por controle, a Força e o volume."""
    valores: dict[str, Any] = {"calados": sorted(calados)}
    for controle, por_controle in sorted((niveis or {}).items()):
        if por_controle:
            valores[controle] = dict(sorted(por_controle.items()))
    _gravar(dados, ARQUIVO_DOS_CONTROLES, valores)


def _ler(arquivo: Path) -> dict[str, Any]:
    try:
        lidas = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return lidas if isinstance(lidas, dict) else {}


def _gravar(dados: Path, nome_do_arquivo: str, valores: dict[str, Any]) -> None:
    """Arquivo novo e ``rename``, em ``0600``."""
    arquivo = dados / nome_do_arquivo
    dados.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix=f".{arquivo.stem}-", suffix=".json", dir=dados)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as saida:
            json.dump(valores, saida, ensure_ascii=False, indent=2)
            saida.write("\n")
        os.chmod(nome, 0o600)
        os.replace(nome, arquivo)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(nome)
        raise
