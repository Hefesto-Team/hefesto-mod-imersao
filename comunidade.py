"""As receitas da comunidade: o índice assinado e a receita do jogo aberto.

O repositório ``hefesto-receitas-imersao`` guarda uma receita por arquivo em
``steam/<chave>/<nome>.json`` e publica o ``indice.json`` com a assinatura ao lado
(``indice.json.minisig``, no formato do minisign: Ed25519 sobre o BLAKE2b-512 do arquivo, com o
comentário de confiança assinado junto). A :class:`Comunidade` baixa o índice uma vez por dia (ou
no «Procurar receitas»; depois de uma busca que falha espera 1 h, 6 h e um dia, e a que dá certo
zera a espera), confere a assinatura com a :data:`CHAVE_PUBLICA` que vem na extensão, e só depois
baixa a receita do jogo aberto, que tem de bater com o tamanho e a soma SHA-256 do
índice e passar de novo pelo validador. A receita que lê a memória espera a chave «Memória neste
jogo» do Hefesto, a mesma das outras receitas, com o aviso de anticheat dele.

A conferência do Ed25519 é a da RFC 8032, em Python puro (só ``hashlib``), e o ``assinar`` é o do
fecho do repositório.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from receita.biblioteca import PASTA_DA_COMUNIDADE
from receita.formato import CHAVE_DE_JOGO, TAMANHO_MAXIMO, ReceitaRecusada, ler_receita

ENDERECO = "https://raw.githubusercontent.com/Hefesto-Team/hefesto-receitas-imersao/main/"
CHAVE_PUBLICA = "RWRsvpXda7nQaYoylSuh7T/EnLZkT+oVI+Snnok9KNqlRsrhojRS+rOF"
ARQUIVO_DO_INDICE = "indice.json"
ARQUIVO_DA_ASSINATURA = "indice.json.minisig"
PASTA_DO_INDICE = "indice-da-comunidade"
TETO_DO_INDICE = 1024 * 1024
TETO_DA_ASSINATURA = 1024
UMA_HORA_S = 60 * 60
UM_DIA_S = 24 * UMA_HORA_S
RECUOS_S = (UMA_HORA_S, 6 * UMA_HORA_S, UM_DIA_S)
CAMINHO_DA_RECEITA = re.compile(r"^steam/(steam_app_[0-9]{1,12})/([a-z0-9][a-z0-9-]{0,47})\.json$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_RAIZ_DE_MENOS_UM = pow(2, (_P - 1) // 4, _P)
Ponto = tuple[int, int, int, int]


class AssinaturaRecusada(ValueError):
    """A assinatura não fecha com a chave pública, ou não está no formato."""


class ReceitaDaComunidadeRecusada(ValueError):
    """A receita baixada não bate com o índice, ou não passa no validador."""


def _somar(a: Ponto, b: Ponto) -> Ponto:
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    pa = (y1 - x1) * (y2 - x2) % _P
    pb = (y1 + x1) * (y2 + x2) % _P
    pc = t1 * 2 * _D * t2 % _P
    pd = z1 * 2 * z2 % _P
    e, f, g, h = pb - pa, pd - pc, pd + pc, pb + pa
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _vezes(escalar: int, ponto: Ponto) -> Ponto:
    saida: Ponto = (0, 1, 1, 0)
    while escalar > 0:
        if escalar & 1:
            saida = _somar(saida, ponto)
        ponto = _somar(ponto, ponto)
        escalar >>= 1
    return saida


def _iguais(a: Ponto, b: Ponto) -> bool:
    return ((a[0] * b[2] - b[0] * a[2]) % _P == 0) and ((a[1] * b[2] - b[1] * a[2]) % _P == 0)


def _x_de(y: int, sinal: int) -> int | None:
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sinal else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _RAIZ_DE_MENOS_UM % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sinal:
        x = _P - x
    return x


_BY = 4 * pow(5, _P - 2, _P) % _P
_BX = _x_de(_BY, 0) or 0
_BASE: Ponto = (_BX, _BY, 1, _BX * _BY % _P)


def _comprimir(ponto: Ponto) -> bytes:
    inverso = pow(ponto[2], _P - 2, _P)
    x, y = ponto[0] * inverso % _P, ponto[1] * inverso % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _descomprimir(bruto: bytes) -> Ponto | None:
    if len(bruto) != 32:
        return None
    y = int.from_bytes(bruto, "little")
    sinal = y >> 255
    y &= (1 << 255) - 1
    x = _x_de(y, sinal)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _h(*partes: bytes) -> int:
    return int.from_bytes(hashlib.sha512(b"".join(partes)).digest(), "little")


def _segredo(semente: bytes) -> tuple[int, bytes]:
    if len(semente) != 32:
        raise ValueError("a semente do Ed25519 tem 32 bytes")
    resumo = hashlib.sha512(semente).digest()
    a = int.from_bytes(resumo[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, resumo[32:]


def publica_da_semente(semente: bytes) -> bytes:
    """A chave pública Ed25519 (32 bytes) da semente secreta."""
    a, _ = _segredo(semente)
    return _comprimir(_vezes(a, _BASE))


def assinar_ed25519(semente: bytes, mensagem: bytes) -> bytes:
    """A assinatura Ed25519 (64 bytes) da mensagem, pela RFC 8032."""
    a, prefixo = _segredo(semente)
    publica = _comprimir(_vezes(a, _BASE))
    r = _h(prefixo, mensagem) % _L
    rr = _comprimir(_vezes(r, _BASE))
    s = (r + _h(rr, publica, mensagem) * a) % _L
    return rr + int.to_bytes(s, 32, "little")


def conferir_ed25519(publica: bytes, mensagem: bytes, assinatura: bytes) -> bool:
    """Se a assinatura Ed25519 fecha com a chave pública, pela RFC 8032."""
    if len(publica) != 32 or len(assinatura) != 64:
        return False
    ponto_a = _descomprimir(publica)
    ponto_r = _descomprimir(assinatura[:32])
    if ponto_a is None or ponto_r is None:
        return False
    s = int.from_bytes(assinatura[32:], "little")
    if s >= _L:
        return False
    h = _h(assinatura[:32], publica, mensagem) % _L
    return _iguais(_vezes(s, _BASE), _somar(ponto_r, _vezes(h, ponto_a)))


def chave_publica_minisign(semente: bytes, ident: bytes) -> str:
    """A chave pública no formato do minisign (a segunda linha do ``.pub``)."""
    if len(ident) != 8:
        raise ValueError("a identidade da chave tem 8 bytes")
    return base64.b64encode(b"Ed" + ident + publica_da_semente(semente)).decode("ascii")


def assinar_minisign(semente: bytes, ident: bytes, mensagem: bytes, confianca: str) -> str:
    """O ``.minisig`` da mensagem: a assinatura do BLAKE2b-512 e o comentário de confiança."""
    assinatura = assinar_ed25519(semente, hashlib.blake2b(mensagem, digest_size=64).digest())
    global_ = assinar_ed25519(semente, assinatura + confianca.encode("utf-8"))
    return (f"untrusted comment: assinatura do indice das receitas\n"
            f"{base64.b64encode(b'ED' + ident + assinatura).decode('ascii')}\n"
            f"trusted comment: {confianca}\n"
            f"{base64.b64encode(global_).decode('ascii')}\n")


def conferir_minisign(mensagem: bytes, minisig: bytes, chave_publica: str) -> str:
    """O comentário de confiança, quando a assinatura fecha; senão, :class:`AssinaturaRecusada`."""
    try:
        publica = base64.b64decode(chave_publica, validate=True)
        linhas = minisig.decode("utf-8").splitlines()
        assinada = base64.b64decode(linhas[1], validate=True)
        global_ = base64.b64decode(linhas[3], validate=True)
    except (ValueError, IndexError, UnicodeDecodeError) as exc:
        raise AssinaturaRecusada("a assinatura não está no formato") from exc
    if len(publica) != 42 or publica[:2] != b"Ed":
        raise AssinaturaRecusada("a chave pública não está no formato")
    if len(assinada) != 74 or assinada[:2] != b"ED":
        raise AssinaturaRecusada("a assinatura não é do BLAKE2b-512 do arquivo")
    if assinada[2:10] != publica[2:10]:
        raise AssinaturaRecusada("a assinatura é de outra chave")
    prefixo = "trusted comment: "
    if not linhas[2].startswith(prefixo):
        raise AssinaturaRecusada("falta o comentário de confiança")
    confianca = linhas[2][len(prefixo):]
    resumo = hashlib.blake2b(mensagem, digest_size=64).digest()
    if not conferir_ed25519(publica[10:], resumo, assinada[10:]):
        raise AssinaturaRecusada("a assinatura não fecha com o arquivo")
    if not conferir_ed25519(publica[10:], assinada[10:] + confianca.encode("utf-8"), global_):
        raise AssinaturaRecusada("o comentário de confiança foi trocado")
    return confianca


@dataclass(frozen=True)
class Entrada:
    """Uma receita do índice: onde mora, a soma, se lê a memória e se o jogo tem anticheat."""

    chave: str
    nome: str
    arquivo: str
    sha256: str
    tamanho: int
    memoria: bool
    anticheat: bool


def ler_o_indice(bruto: bytes, minisig: bytes, chave_publica: str = CHAVE_PUBLICA) -> list[Entrada]:
    """As entradas do índice, só depois de a assinatura fechar."""
    conferir_minisign(bruto, minisig, chave_publica)
    try:
        dados = json.loads(bruto)
        itens = dados["receitas"] if dados.get("formato") == 1 else None
    except (ValueError, AttributeError, KeyError, TypeError) as exc:
        raise AssinaturaRecusada("o índice assinado não está no formato") from exc
    if not isinstance(itens, list):
        raise AssinaturaRecusada("o índice assinado não está no formato")
    entradas: list[Entrada] = []
    for item in itens:
        with contextlib.suppress(KeyError, TypeError, ValueError):
            achado = CAMINHO_DA_RECEITA.match(item["arquivo"])
            if (achado and achado.group(1) == item["chave"] and SHA256.match(item["sha256"])
                    and isinstance(item["tamanho"], int) and 0 < item["tamanho"] <= TAMANHO_MAXIMO):
                entradas.append(Entrada(item["chave"], achado.group(2), item["arquivo"],
                                        item["sha256"], item["tamanho"],
                                        item.get("memoria") is True,
                                        item.get("anticheat") is True))
    return entradas


def baixar_da_internet(endereco: str, teto: int) -> bytes:
    """O arquivo do repositório, até ``teto`` bytes; passar do teto recusa."""
    if not endereco.startswith(ENDERECO):
        raise ValueError("a extensão só baixa do repositório das receitas")
    pedido = urllib.request.Request(endereco, headers={"User-Agent": "hefesto-mod-imersao"})
    with urllib.request.urlopen(pedido, timeout=15) as resposta:
        corpo: bytes = resposta.read(teto + 1)
    if len(corpo) > teto:
        raise ValueError(f"o arquivo passa de {teto} bytes")
    return corpo


def _gravar(arquivo: Path, bruto: bytes) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_name(arquivo.name + ".novo")
    temporario.write_bytes(bruto)
    os.replace(temporario, arquivo)


class Comunidade:
    """O índice e as receitas da comunidade em ``$HEFESTO_MOD_DADOS``.

    O índice conferido mora em ``indice-da-comunidade/``; a receita do jogo, em
    ``comunidade/<chave>.json``, onde a
    :class:`~receita.biblioteca.Biblioteca` a acha depois da sua e da estudada.
    """

    def __init__(self, dados: Path, baixar: Callable[[str, int], bytes] | None = None,
                 chave_publica: str = CHAVE_PUBLICA,
                 relogio: Callable[[], float] = time.time) -> None:
        self.dados = dados
        self._baixar = baixar
        self.chave_publica = chave_publica
        self._relogio = relogio
        self._falhas = 0
        self._falhou_em = 0.0

    def baixar(self, endereco: str, teto: int) -> bytes:
        return (self._baixar or baixar_da_internet)(endereco, teto)

    @property
    def pasta_do_indice(self) -> Path:
        return self.dados / PASTA_DO_INDICE

    def _no_recuo(self) -> bool:
        """Se a última busca que falhou ainda está dentro da espera dela."""
        if not self._falhas:
            return False
        return self._relogio() - self._falhou_em < RECUOS_S[min(self._falhas, len(RECUOS_S)) - 1]

    def vencido(self) -> bool:
        """Se o índice guardado passou de um dia, ou ainda não veio."""
        try:
            marca = (self.pasta_do_indice / ARQUIVO_DO_INDICE).stat().st_mtime
        except OSError:
            return True
        return self._relogio() - marca >= UM_DIA_S

    def indice_conferido(self) -> list[Entrada] | None:
        """O índice guardado, conferido de novo; ``None`` quando falta ou não fecha."""
        with contextlib.suppress(OSError, AssinaturaRecusada):
            return ler_o_indice((self.pasta_do_indice / ARQUIVO_DO_INDICE).read_bytes(),
                                (self.pasta_do_indice / ARQUIVO_DA_ASSINATURA).read_bytes(),
                                self.chave_publica)
        return None

    def entradas(self) -> list[Entrada]:
        """O índice guardado e conferido; vazio quando falta ou não fecha."""
        return self.indice_conferido() or []

    def atualizar_o_indice(self) -> list[Entrada]:
        """Baixa o índice e a assinatura; só grava o que fecha com a chave pública."""
        bruto = self.baixar(ENDERECO + ARQUIVO_DO_INDICE, TETO_DO_INDICE)
        minisig = self.baixar(ENDERECO + ARQUIVO_DA_ASSINATURA, TETO_DA_ASSINATURA)
        entradas = ler_o_indice(bruto, minisig, self.chave_publica)
        _gravar(self.pasta_do_indice / ARQUIVO_DA_ASSINATURA, minisig)
        _gravar(self.pasta_do_indice / ARQUIVO_DO_INDICE, bruto)
        return entradas

    def entrada_do_jogo(self, chave: str, entradas: list[Entrada] | None = None) -> Entrada | None:
        """A receita do jogo no índice (as ``entradas`` dadas ou as do guardado), a de nome menor."""
        lista = self.entradas() if entradas is None else entradas
        do_jogo = sorted((e for e in lista if e.chave == chave), key=lambda e: e.nome)
        return do_jogo[0] if do_jogo else None

    def baixar_a_receita(self, entrada: Entrada) -> bool:
        """A receita do índice em ``comunidade/<chave>.json``; ``False`` quando já estava igual."""
        arquivo = self.dados / PASTA_DA_COMUNIDADE / f"{entrada.chave}.json"
        with contextlib.suppress(OSError):
            if hashlib.sha256(arquivo.read_bytes()).hexdigest() == entrada.sha256:
                return False
        bruto = self.baixar(ENDERECO + entrada.arquivo, entrada.tamanho)
        if len(bruto) != entrada.tamanho or hashlib.sha256(bruto).hexdigest() != entrada.sha256:
            raise ReceitaDaComunidadeRecusada(
                f"{entrada.arquivo} não bate com a soma do índice assinado")
        try:
            receita = ler_receita(bruto)
        except ReceitaRecusada as exc:
            raise ReceitaDaComunidadeRecusada(f"{entrada.arquivo} não passa no validador:\n{exc}") from exc
        jogo = receita.dados.get("jogo", {})
        if jogo.get("chave") != entrada.chave:
            raise ReceitaDaComunidadeRecusada(f"{entrada.arquivo} é de outro jogo")
        if (jogo.get("leitura_de_memoria") == "pede") != entrada.memoria:  # (noqa-acento)
            raise ReceitaDaComunidadeRecusada(f"{entrada.arquivo} esconde a leitura da memória")
        _gravar(arquivo, bruto)
        return True

    def esquecer(self, chave: str) -> None:
        """Apaga a receita do jogo que o índice conferido deixou de listar."""
        with contextlib.suppress(OSError):
            (self.dados / PASTA_DA_COMUNIDADE / f"{chave}.json").unlink()

    def procurar(self, chave: str | None, agora: bool = False) -> dict[str, Any]:
        """O «Procurar receitas» (``agora``) ou a volta diária, para o jogo ``chave``. A busca que
        falha, no índice ou na receita, começa ou alonga a espera de :data:`RECUOS_S`, em que só o
        ``agora`` vai à rede, e a que dá certo a zera."""
        if not agora and self._no_recuo():
            return {"tipo": "procurado", "achou": False}
        try:
            resultado = self._procurar(chave, agora)
        except (AssinaturaRecusada, ReceitaDaComunidadeRecusada) as exc:
            resultado = {"tipo": "recusado", "frase": str(exc)}
        except (OSError, ValueError) as exc:
            resultado = {"tipo": "erro", "frase": "as receitas da comunidade não vieram",
                         "detalhe": str(exc)}
        if resultado["tipo"] == "procurado":
            self._falhas = 0
        else:
            self._falhas += 1
            self._falhou_em = self._relogio()
        return resultado

    def _procurar(self, chave: str | None, agora: bool) -> dict[str, Any]:
        entradas = self.indice_conferido()
        if agora or entradas is None or self.vencido():
            entradas = self.atualizar_o_indice()
        if chave is None or not CHAVE_DE_JOGO.match(chave):
            return {"tipo": "procurado", "achou": False}
        entrada = self.entrada_do_jogo(chave, entradas)
        if entrada is None:
            self.esquecer(chave)
            return {"tipo": "procurado", "achou": False}
        nova = self.baixar_a_receita(entrada)
        return {"tipo": "procurado", "achou": True, "nova": nova, "nome": entrada.nome,
                "memoria": entrada.memoria}
