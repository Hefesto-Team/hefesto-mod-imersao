"""O Estúdio caça o que o jogo esconde: o valor na memória, o som que estala e o canto da tela.

Os três caçadores seguem a mesma regra: guarda o que muda COM o gesto e descarta o que muda SEM
ele. A página guia com frases curtas («perca vida agora», «agora não faça nada», «recupere vida»)
e o gesto se marca pelo botão do meio do controle.

* :class:`CacadorDeValor` só existe com a chave «Memória» do jogo ligada. Ele pede à porta uma
  varredura de candidatos (``memoria.varrer``) e estreita a lista a cada gesto; o leitor guarda os
  candidatos do lado dele e devolve só a contagem e uma ficha, e o endereço só sai quando sobra um.
  :class:`VarredorDeRetratos` é a referência local desse contrato, sobre retratos da memória.
* :class:`CacadorDeSom` guarda a impressão do estalo que se repete com o gesto, em números (até
  4 KB), nunca o áudio.
* :class:`CacadorDeTela` acha a região que muda com o gesto e não sem ele, em frações de 0 a 1.

O achado vira um ``estado`` na receita de quem joga, com o nome que a pessoa der
(:func:`para_a_receita`).
"""
from __future__ import annotations

import base64
import contextlib
import json
import math
import os
import re
import secrets
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import opcoes as ajustes
from receita import impressao as impressoes

TIPOS: dict[str, tuple[str, int]] = {"i8": ("b", 1), "i16": ("h", 2), "i32": ("i", 4),
                                     "f32": ("f", 4)}
LARGURA_DOS_INTEIROS = ("i32", "i16", "i8")
COMPARACOES = ("igual", "subiu", "desceu", "nao_mudou")
GESTOS = ("parado", "perder", "recuperar")
FRASES = {
    "parado": "agora não faça nada",
    "perder": "perca vida agora",
    "recuperar": "recupere vida",
    "cheia": "fique com a vida cheia",
    "som": "faça o som agora",
    "achou": "achei",
    "nada": "não achei: tente de novo",
}
ROTEIRO_DO_VALOR = ("parado", "perder", "parado", "perder", "recuperar")
ROTEIRO_DA_TELA = ("cheia", "parado", "perder")
MARCAS_DO_SOM = 3
JANELA_ANTES_MS = 2500.0
JANELA_DEPOIS_MS = 500.0
GUARDA_DO_SOM_MS = 30_000.0
PARECIDO = 0.9
TOLERANCIA_DA_TELA = 40
TETO_DA_REGIAO = 0.25
FAIXA_DO_REAL = (1e-3, 1e7)
TOPICO_DO_ACHADO = {"valor": "jogo.memoria", "som": "jogo.som", "tela": "jogo.tela"}


class MemoriaDesligada(RuntimeError):
    """O caçador de valor pede a chave «Memória» do jogo, que nasce desligada."""


@dataclass(frozen=True)
class Achado:
    """O que um caçador achou: ``tipo`` é ``valor``, ``som`` ou ``tela``."""

    tipo: str
    dados: dict[str, Any]


Pedir = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class VarredorDeRetratos:
    """A varredura do leitor de memória sobre retratos (``ler`` devolve a memória de agora).

    O contrato é o da porta: :meth:`varrer` sem ``token`` começa com todos os valores alinhados do
    ``tipo``; com ``token``, guarda só os que obedecem à ``comparacao`` desde o retrato anterior. A
    resposta traz a ``token`` e a contagem de ``candidatos``; ``endereco`` e ``valor`` só quando
    sobra um.
    """

    def __init__(self, ler: Callable[[], bytes], modulo: str = "retrato", base: int = 0) -> None:
        self._ler = ler
        self.modulo = modulo
        self.base = base
        self._fichas: dict[str, tuple[str, list[int], memoryview]] = {}

    async def varrer(self, tipo: str, comparacao: str, token: str | None = None,
                     valor: float | None = None) -> dict[str, Any]:
        if tipo not in TIPOS or comparacao not in COMPARACOES:
            raise ValueError(f"varredura desconhecida: {tipo} {comparacao}")
        letra, largura = TIPOS[tipo]
        retrato = bytes(self._ler())
        inteiro = memoryview(retrato[:len(retrato) // largura * largura])
        valores = inteiro.cast(letra)  # type: ignore[call-overload]
        if token is None:
            candidatos = list(range(len(valores)))
        else:
            if token not in self._fichas or self._fichas[token][0] != tipo:
                raise ValueError("ficha desconhecida")
            _, antes, velhos = self._fichas.pop(token)
            candidatos = _filtrar(antes, velhos, valores, comparacao, valor)
        ficha = secrets.token_hex(8)
        self._fichas[ficha] = (tipo, candidatos, valores)
        resposta: dict[str, Any] = {"token": ficha, "candidatos": len(candidatos)}
        if len(candidatos) == 1:
            resposta.update(endereco=hex(self.base + candidatos[0] * largura),
                            modulo=self.modulo, base=hex(candidatos[0] * largura),
                            valor=valores[candidatos[0]])
        return resposta


def _filtrar(candidatos: list[int], velhos: memoryview, novos: memoryview, comparacao: str,
             valor: float | None) -> list[int]:
    if comparacao == "nao_mudou":
        return [i for i in candidatos if novos[i] == velhos[i]]
    if comparacao == "desceu":
        return [i for i in candidatos if novos[i] < velhos[i]]
    if comparacao == "subiu":
        return [i for i in candidatos if novos[i] > velhos[i]]
    return [i for i in candidatos if novos[i] == valor]


class VarredorDaPorta:
    """A varredura pedida ao leitor de memória do Hefesto (``memoria.varrer``)."""

    def __init__(self, pedir: Pedir) -> None:
        self._pedir = pedir

    async def varrer(self, tipo: str, comparacao: str, token: str | None = None,
                     valor: float | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"tipo": tipo, "comparacao": comparacao}
        if token is not None:
            params["token"] = token
        if valor is not None:
            params["valor"] = valor
        return await self._pedir("memoria.varrer", params)


Varredor = VarredorDeRetratos | VarredorDaPorta


@dataclass
class _Ramo:
    tipo: str
    sobe: bool
    token: str | None = None
    candidatos: int = -1
    ultimo: dict[str, Any] = field(default_factory=dict)

    def comparacao(self, gesto: str) -> str:
        if gesto == "parado":
            return "nao_mudou"
        perde = "subiu" if self.sobe else "desceu"
        if gesto == "perder":
            return perde
        return "desceu" if perde == "subiu" else "subiu"


class CacadorDeValor:
    """O valor da memória que acompanha os gestos, em até cinco deles."""

    def __init__(self, varredor: Varredor, memoria_ligada: bool) -> None:
        if not memoria_ligada:
            raise MemoriaDesligada("o caçador de valor pede a chave «Memória» do jogo ligada")
        self._varredor = varredor
        self._ramos = [_Ramo(tipo, sobe) for tipo in TIPOS for sobe in (False, True)]
        self.gestos: list[str] = []

    @property
    def candidatos(self) -> int:
        return sum(max(r.candidatos, 0) for r in self._ramos)

    async def comecar(self) -> None:
        for ramo in self._ramos:
            await self._varrer(ramo, "nao_mudou")

    async def gesto(self, qual: str) -> None:
        if qual not in GESTOS:
            raise ValueError(f"gesto desconhecido: {qual}")
        self.gestos.append(qual)
        for ramo in self._ramos:
            if ramo.candidatos > 0:
                await self._varrer(ramo, ramo.comparacao(qual))

    async def _varrer(self, ramo: _Ramo, comparacao: str) -> None:
        resposta = await self._varredor.varrer(ramo.tipo, comparacao, ramo.token)
        ramo.token = resposta.get("token")
        ramo.candidatos = int(resposta.get("candidatos", 0))
        ramo.ultimo = resposta

    def achado(self) -> Achado | None:
        """O valor achado: um endereço só, com dois «perder» e um «parado» pelo menos."""
        if self.gestos.count("perder") < 2 or "parado" not in self.gestos:
            return None
        por_endereco: dict[str, _Ramo] = {}
        for ramo in self._ramos:
            if ramo.candidatos != 1 or "endereco" not in ramo.ultimo:
                continue
            if ramo.tipo == "f32" and not _real_plausivel(ramo.ultimo.get("valor")):
                continue
            atual = por_endereco.get(ramo.ultimo["endereco"])
            if atual is None or _mais_largo(ramo.tipo, atual.tipo):
                por_endereco[ramo.ultimo["endereco"]] = ramo
        if len(por_endereco) != 1:
            return None
        ramo = next(iter(por_endereco.values()))
        ultimo = ramo.ultimo
        return Achado("valor", {"tipo": ramo.tipo, "endereco": ultimo["endereco"],
                                "modulo": str(ultimo.get("modulo") or "principal"),  # (noqa-acento)
                                "base": str(ultimo.get("base") or ultimo["endereco"]),
                                "valor": ultimo.get("valor"), "sobe": ramo.sobe})


def _mais_largo(novo: str, atual: str) -> bool:
    if atual == "f32":
        return novo != "f32"
    if novo == "f32":
        return False
    return LARGURA_DOS_INTEIROS.index(novo) < LARGURA_DOS_INTEIROS.index(atual)


def _real_plausivel(valor: Any) -> bool:
    if not isinstance(valor, (int, float)) or not math.isfinite(valor):
        return False
    return valor == 0 or FAIXA_DO_REAL[0] <= abs(valor) <= FAIXA_DO_REAL[1]


@dataclass(frozen=True)
class _Estalo:
    t_ms: float
    bandas: tuple[float, ...]


class CacadorDeSom:
    """O estalo que se repete com o gesto, guardado como impressão das bandas."""

    def __init__(self) -> None:
        self._estalos: list[_Estalo] = []
        self.marcas: list[float] = []

    def ouvir(self, dados: dict[str, Any], t_ms: float) -> None:
        bandas = dados.get("bandas")
        if dados.get("evento") != "estalo" or not isinstance(bandas, list) or not bandas:
            return
        if not all(isinstance(b, (int, float)) and not isinstance(b, bool) for b in bandas):
            return
        normal = impressoes.normalizar(bandas)
        if not any(normal):
            return
        self._estalos.append(_Estalo(t_ms, tuple(normal)))
        corte = t_ms - GUARDA_DO_SOM_MS
        self._estalos = [e for e in self._estalos if e.t_ms >= corte]

    def marcar(self, t_ms: float) -> None:
        self.marcas.append(t_ms)

    def _na_janela(self, estalo: _Estalo, marca: float) -> bool:
        return marca - JANELA_ANTES_MS <= estalo.t_ms <= marca + JANELA_DEPOIS_MS

    def achar(self) -> Achado | None:
        """A impressão do estalo presente em toda janela de gesto e raro fora delas."""
        if len(self.marcas) < MARCAS_DO_SOM:
            return None
        dentro = [e for e in self._estalos if any(self._na_janela(e, m) for m in self.marcas)]
        fora = [e for e in self._estalos if e not in dentro]
        melhor: tuple[int, list[_Estalo]] | None = None
        for candidato in dentro:
            iguais = [e for e in dentro
                      if impressoes.cosseno(e.bandas, candidato.bandas) >= PARECIDO]
            if not all(any(self._na_janela(e, m) for e in iguais) for m in self.marcas):
                continue
            de_fora = sum(1 for e in fora
                          if impressoes.cosseno(e.bandas, candidato.bandas) >= PARECIDO)
            if de_fora > max(1, len(self.marcas) // 3):
                continue
            if melhor is None or de_fora < melhor[0]:
                melhor = (de_fora, iguais)
        if melhor is None:
            return None
        iguais = melhor[1]
        media = [sum(e.bandas[i] for e in iguais) / len(iguais) for i in range(len(iguais[0].bandas))]
        return Achado("som", {"impressao": impressoes.gravar(media)})  # (noqa-acento)


@dataclass(frozen=True)
class Retrato:
    """Um quadro da tela em ``largura × altura`` pontos RGB."""

    largura: int
    altura: int
    rgb: bytes

    @classmethod
    def da_porta(cls, dados: dict[str, Any]) -> Retrato:
        largura, altura = int(dados["largura"]), int(dados["altura"])
        rgb = base64.b64decode(dados["rgb"])
        if largura <= 0 or altura <= 0 or len(rgb) != largura * altura * 3:
            raise ValueError("retrato fora do formato")
        return cls(largura, altura, rgb)

    def ponto(self, x: int, y: int) -> tuple[int, int, int]:
        i = (y * self.largura + x) * 3
        return (self.rgb[i], self.rgb[i + 1], self.rgb[i + 2])


def _mudou(a: Retrato, b: Retrato) -> list[bool]:
    return [max(abs(p - q) for p, q in zip(a.ponto(x, y), b.ponto(x, y))) > TOLERANCIA_DA_TELA
            for y in range(a.altura) for x in range(a.largura)]


class CacadorDeTela:
    """A região da tela que muda com o gesto e não muda sem ele."""

    def __init__(self) -> None:
        self.retratos: dict[str, Retrato] = {}

    def guardar(self, papel: str, retrato: Retrato) -> None:
        if papel not in ROTEIRO_DA_TELA:
            raise ValueError(f"papel desconhecido: {papel}")
        if self.retratos and next(iter(self.retratos.values())).largura != retrato.largura:
            raise ValueError("os retratos têm de ter o mesmo tamanho")
        self.retratos[papel] = retrato

    def achar(self) -> Achado | None:
        if any(p not in self.retratos for p in ROTEIRO_DA_TELA):
            return None
        cheia, parado, perdeu = (self.retratos[p] for p in ROTEIRO_DA_TELA)
        largura, altura = cheia.largura, cheia.altura
        sem_gesto = _mudou(cheia, parado)
        mascara = [c and not s for c, s in zip(_mudou(cheia, perdeu), sem_gesto)]
        melhor: tuple[float, tuple[int, int, int, int]] | None = None
        for caixa, area in _componentes(mascara, largura, altura):
            if area > TETO_DA_REGIAO * largura * altura:
                continue
            x0, y0, x1, y1 = caixa
            w, h = x1 - x0 + 1, y1 - y0 + 1
            if area < 2:
                continue
            alongada = max(w, h) / min(w, h)
            borda = 1 - min(x0, largura - 1 - x1, y0, altura - 1 - y1) / (min(largura, altura) / 2)
            nota = area * (1 + min(alongada, 8) / 4) * (1 + max(borda, 0))
            if melhor is None or nota > melhor[0]:
                melhor = (nota, caixa)
        if melhor is None:
            return None
        x0, y0, x1, y1 = melhor[1]
        regiao = {"x": x0 / largura, "y": y0 / altura, "w": (x1 - x0 + 1) / largura,
                  "h": (y1 - y0 + 1) / altura}
        cx, cy = regiao["x"] + regiao["w"] / 2, regiao["y"] + regiao["h"] / 2
        ancora = f"canto_{'sup' if cy < 0.5 else 'inf'}_{'esq' if cx < 0.5 else 'dir'}"
        return Achado("tela", {"regiao": {"ancora": ancora,
                                          **{k: round(v, 4) for k, v in regiao.items()},
                                          "referencia": [largura, altura]}})  # (noqa-acento)


def _componentes(mascara: Sequence[bool], largura: int,
                 altura: int) -> list[tuple[tuple[int, int, int, int], int]]:
    vistos = [False] * len(mascara)
    saida: list[tuple[tuple[int, int, int, int], int]] = []
    for inicio, aceso in enumerate(mascara):
        if not aceso or vistos[inicio]:
            continue
        vistos[inicio] = True
        pilha, area = [inicio], 0
        x0 = y0 = 1 << 30
        x1 = y1 = -1
        while pilha:
            i = pilha.pop()
            x, y = i % largura, i // largura
            area += 1
            x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                j = ny * largura + nx
                if 0 <= nx < largura and 0 <= ny < altura and mascara[j] and not vistos[j]:
                    vistos[j] = True
                    pilha.append(j)
        saida.append(((x0, y0, x1, y1), area))
    return saida


def ident_do_nome(nome: str) -> str:
    """O nome que a pessoa deu, como identificador da receita (``Vida baixa`` → ``vida_baixa``)."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    ident = re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")
    if not ident or not ident[0].isalpha():
        ident = f"achado_{ident}".rstrip("_")
    return ident[:24].rstrip("_")


def para_a_receita(receita: dict[str, Any] | None, chave: str, nome: str,
                   achado: Achado) -> dict[str, Any]:
    """A receita de quem joga com o achado como sentido e o ``estado`` com o nome dado."""
    dados: dict[str, Any] = dict(receita) if receita else {
        "formato": 1, "motor": ">=1,<2", "jogo": {"chave": chave}}
    dados["jogo"] = {**dados.get("jogo", {}), "chave": chave}
    estado = ident_do_nome(nome)
    sinal = f"{estado}_lido"
    sentidos = dict(dados.get("sentidos", {}))
    estados = dict(dados.get("estados", {}))
    permissoes = list(dados.get("permissoes", []))  # (noqa-acento)
    if achado.tipo == "valor":
        cheio = achado.dados.get("valor")
        leitura = {k: achado.dados[k] for k in ("tipo", "modulo", "base")}  # (noqa-acento)
        sentidos[sinal] = {"de": "jogo.memoria", "especie": "nivel", "leitura": leitura}
        if isinstance(cheio, (int, float)) and cheio > 0 and not achado.dados.get("sobe"):
            sentidos[sinal]["escala"] = [0, cheio]
            estados[estado] = {"quando": f"{sinal} < 0.3", "histerese": 0.05}
        else:
            estados[estado] = {"quando": f"{sinal} > 0", "histerese": 0.05}
        dados["jogo"]["leitura_de_memoria"] = "pede"  # (noqa-acento)
    elif achado.tipo == "som":
        sentidos[sinal] = {"de": "jogo.som", "especie": "evento",
                           "impressao": achado.dados["impressao"]}  # (noqa-acento)
        estados[estado] = {"quando": sinal, "minimo_ms": 1500}
    elif achado.tipo == "tela":
        sentidos[sinal] = {"de": "jogo.tela", "especie": "nivel", "regiao": achado.dados["regiao"]}
        estados[estado] = {"quando": f"{sinal} > 0.5", "histerese": 0.1}
    else:
        raise ValueError(f"achado desconhecido: {achado.tipo}")
    topico = TOPICO_DO_ACHADO[achado.tipo]
    if f"ler:{topico}" not in permissoes:
        permissoes.append(f"ler:{topico}")
    dados.update(sentidos=sentidos, estados=estados, permissoes=permissoes)  # (noqa-acento)
    return dados


class Estudio:
    """A sessão do Estúdio: as mensagens da página, os gestos marcados e o achado guardado.

    A página manda ``abrir``, ``comecar`` (com o ``cacador``), ``passo``, ``guardar`` (com o
    ``nome``) e ``cancelar``; o botão do meio do controle vale um ``passo``. Cada resposta traz a
    ``frase`` da vez. O achado guardado vai à receita de quem joga, em
    ``$HEFESTO_MOD_DADOS/receitas/<chave>.json``, só depois de validado, e liga o sentido que a
    receita passa a ler (:func:`opcoes.consentir`).
    """

    def __init__(self, pedir: Pedir, receitas: Path | None,
                 validar: Callable[[bytes], object]) -> None:
        self._pedir = pedir
        self.receitas = receitas
        self._validar = validar
        self.jogo: str | None = None
        self.memoria_ligada = False
        self.cacador: str | None = None
        self._valor: CacadorDeValor | None = None
        self._som: CacadorDeSom | None = None
        self._tela: CacadorDeTela | None = None
        self._passo = 0
        self.achado: Achado | None = None

    @property
    def ativo(self) -> bool:
        return self.cacador is not None and self.achado is None

    def cacadores(self) -> list[str]:
        return ["valor", "som", "tela"] if self.memoria_ligada else ["som", "tela"]

    def _roteiro(self) -> tuple[str, ...]:
        if self.cacador == "valor":
            return ROTEIRO_DO_VALOR
        if self.cacador == "tela":
            return ROTEIRO_DA_TELA
        return ("perder",) * MARCAS_DO_SOM

    def _vez(self) -> dict[str, Any]:
        roteiro = self._roteiro()
        return {"tipo": "passo", "cacador": self.cacador, "passo": self._passo + 1,
                "de": len(roteiro), "frase": FRASES[roteiro[self._passo]]}

    def cancelar(self) -> None:
        self.cacador, self._valor, self._som, self._tela = None, None, None, None
        self._passo, self.achado = 0, None

    def ouvir(self, dados: dict[str, Any], t_ms: float) -> None:
        if self._som is not None and self.achado is None:
            self._som.ouvir(dados, t_ms)

    async def mensagem(self, pedido: dict[str, Any], t_ms: float) -> dict[str, Any]:
        tipo = pedido.get("tipo")
        if tipo == "abrir":
            return {"tipo": "estudio", "jogo": self.jogo, "cacadores": self.cacadores(),
                    "ativo": self.cacador}
        if tipo == "cancelar":
            self.cancelar()
            return {"tipo": "cancelado"}
        if tipo == "comecar":
            return await self._comecar(pedido.get("cacador"))
        if tipo == "passo":
            return await self.marca(t_ms) or {"tipo": "erro", "frase": "nada em andamento"}
        if tipo == "guardar":
            return self._guardar(pedido.get("nome"))
        return {"tipo": "erro", "frase": "pedido desconhecido"}

    async def _comecar(self, cacador: Any) -> dict[str, Any]:
        if self.jogo is None:
            return {"tipo": "erro", "frase": "abra o jogo primeiro"}
        if cacador not in self.cacadores():
            return {"tipo": "erro", "frase": "ligue a chave «Memória» do jogo para achar o valor"
                    if cacador == "valor" else "caçador desconhecido"}
        self.cancelar()
        self.cacador = str(cacador)
        if cacador == "valor":
            self._valor = CacadorDeValor(VarredorDaPorta(self._pedir), self.memoria_ligada)
            await self._valor.comecar()
        elif cacador == "som":
            self._som = CacadorDeSom()
        else:
            self._tela = CacadorDeTela()
        return self._vez()

    async def marca(self, t_ms: float) -> dict[str, Any] | None:
        """O gesto de agora está feito: o caçador anda, e a resposta é a frase seguinte."""
        if not self.ativo:
            return None
        gesto = self._roteiro()[self._passo]
        if self._valor is not None:
            await self._valor.gesto(gesto)
        elif self._som is not None:
            self._som.marcar(t_ms)
        elif self._tela is not None:
            self._tela.guardar(gesto, Retrato.da_porta(await self._pedir("tela.retrato", {})))
        self._passo += 1
        if self._passo < len(self._roteiro()):
            return self._vez()
        achou = (self._valor.achado() if self._valor else self._som.achar() if self._som
                 else self._tela.achar() if self._tela else None)
        if achou is None:
            cacador = self.cacador
            self.cancelar()
            return {"tipo": "nada", "cacador": cacador, "frase": FRASES["nada"]}
        self.achado = achou
        return {"tipo": "achou", "cacador": self.cacador, "frase": FRASES["achou"]}

    def _guardar(self, nome: Any) -> dict[str, Any]:
        if self.achado is None or self.jogo is None:
            return {"tipo": "erro", "frase": "nada achado para guardar"}
        if not isinstance(nome, str) or not nome.strip() or len(nome) > 40:
            return {"tipo": "erro", "frase": "dê um nome ao que achou"}
        if self.receitas is None:
            return {"tipo": "erro", "frase": "sem pasta de dados"}
        arquivo = self.receitas / f"{self.jogo}.json"
        atual: dict[str, Any] | None = None
        with contextlib.suppress(OSError, ValueError):
            lido = json.loads(arquivo.read_text(encoding="utf-8"))
            atual = lido if isinstance(lido, dict) else None
        nova = para_a_receita(atual, self.jogo, nome, self.achado)
        bruto = json.dumps(nova, ensure_ascii=False, indent=2).encode("utf-8")
        try:
            self._validar(bruto)
        except ValueError as exc:
            return {"tipo": "erro", "frase": f"a receita não fecha: {exc}"}
        self.receitas.mkdir(parents=True, exist_ok=True)
        temporario = arquivo.with_suffix(".json.novo")
        temporario.write_bytes(bruto)
        os.replace(temporario, arquivo)
        ajustes.consentir(self.receitas.parent, TOPICO_DO_ACHADO[self.achado.tipo])
        estado = ident_do_nome(nome)
        self.cancelar()
        return {"tipo": "guardado", "estado": estado, "arquivo": arquivo.name}
