"""O motor de receitas: sentidos → estado da cena → regras → efeitos, num laço de 60 Hz.

O :meth:`Motor.passo` é puro no tempo: recebe o instante e devolve o vencedor de cada vaga
(controle, canal e lado). Quem o chama a 60 Hz é :func:`rodar`, que entrega os vencedores à
:class:`~motor.saida.Saida`. Um evento vale um tique; um efeito sem ``dura_ms`` vale enquanto a
regra vale, e nunca menos que :data:`DURACAO_MINIMA_MS`. Os sentidos universais que a receita lê
recebem cada evento da porta e o tique, e o que eles derivam entra no mesmo tique.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import sentidos as universais
from efeitos import luzes
from motor import efeitos as catalogo
from motor.arbitragem import Pedido, Vaga, decidir
from motor.estados import Acumulador, Estado, continua_com_histerese
from motor.saida import Saida
from receita import expressao
from receita.formato import Receita

HZ = 60
DURACAO_MINIMA_MS = 250.0
_LADOS = {"esquerdo": -1.0, "direito": 1.0}


@dataclass
class Leitura:
    valor: float = 0.0
    lado: float = 0.0
    forca: float = 0.0
    jogador: float = 0.0
    uniq: str | None = None
    disparou: bool = False
    anterior: float = 0.0
    t: float | None = None


@dataclass
class Ativacao:
    regra: int
    efeito: str
    alvos: tuple[str, ...]
    inicio_ms: float
    fim_ms: float | None
    t_do_jogo: float | None = None


@dataclass
class _Regra:
    valia: bool = False
    disparou_em: float | None = None
    aceita: bool = False


@dataclass
class _Evento:
    topico: str
    nome: str
    uniq: str | None
    dados: dict[str, Any] = field(default_factory=dict)


def _campo(dados: Any, caminho: str) -> Any:
    for parte in caminho.split("."):
        if isinstance(dados, dict) and parte in dados:
            dados = dados[parte]
        elif isinstance(dados, list) and parte.isdigit() and int(parte) < len(dados):
            dados = dados[int(parte)]
        else:
            return None
    return dados


class Motor:
    """Uma receita viva: o que ela leu, os estados e os efeitos ativos."""

    def __init__(self, receita: Receita, opcoes: dict[str, Any] | None = None) -> None:
        self.receita = receita
        self.opcoes = dict(opcoes or {})
        self.sentidos: dict[str, Any] = receita.secao("sentidos")
        self.leituras = {ident: Leitura() for ident in self.sentidos}
        self.valores: dict[str, float] = {}
        self.estados = {ident: Estado(float(e.get("minimo_ms", 0)))
                        for ident, e in receita.secao("estados").items()}
        self.acumuladores = {
            ident: Acumulador(float(d["acumula"]["passo"]), float(d["acumula"]["meia_vida_ms"]))
            for ident, d in receita.secao("derivados").items() if "acumula" in d}
        self.regras = [_Regra() for _ in receita.regras]
        self.ativas: list[Ativacao] = []
        self.jogadores: dict[str, int] = {}
        self._fila: list[_Evento] = []
        self.universais = universais.criar(s["de"] for s in self.sentidos.values())
        self.vibrando: frozenset[str] = frozenset()

    def controles(self, lista: list[dict[str, Any]]) -> None:
        """Os controles conectados agora, ``[{uniq, jogador}]``."""
        self.jogadores = {c["uniq"]: int(c.get("jogador") or 0) for c in lista
                          if isinstance(c.get("uniq"), str)}

    def evento(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any]) -> None:
        self._fila.append(_Evento(topico, nome, uniq, dados if isinstance(dados, dict) else {}))

    def _ler_evento(self, evento: _Evento) -> None:
        for ident, sentido in self.sentidos.items():
            if sentido["de"] != evento.topico:
                continue
            if "nome" in sentido and sentido["nome"] != evento.nome:
                continue
            leitura = self.leituras[ident]
            valor = 1.0
            if "campo" in sentido:
                bruto = _campo(evento.dados, sentido["campo"])
                if bruto is None:
                    continue
                if "igual" in sentido:
                    valor = float(str(bruto) == sentido["igual"])
                    if sentido["especie"] == "evento" and not valor:
                        continue
                elif isinstance(bruto, (int, float)):
                    valor = float(bruto)
                else:
                    continue
                escala = sentido.get("escala")
                if escala:
                    valor = min(1.0, max(0.0, (valor - escala[0]) / (escala[1] - escala[0])))
            marca = evento.dados.get("t")
            if isinstance(marca, (int, float)) and not isinstance(marca, bool):
                leitura.t = float(marca)
            if evento.uniq is not None:
                leitura.uniq = evento.uniq
                leitura.jogador = float(self.jogadores.get(evento.uniq, 0))
            lado = evento.dados.get("lado")
            if lado in _LADOS:
                leitura.lado = _LADOS[lado]
            if sentido["especie"] != "evento":
                leitura.valor = valor
                continue
            limiar = sentido.get("limiar")
            if limiar is not None:
                cruzou = valor >= limiar > leitura.anterior
                leitura.anterior = valor
                if not cruzou:
                    continue
            leitura.disparou = True
            leitura.forca = valor

    def _ler_nome(self, ident: str, campo: str | None) -> float:
        leitura = self.leituras.get(ident)
        if leitura is None:
            return self.valores.get(ident, 0.0)
        if campo in ("lado", "forca", "jogador"):
            return float(getattr(leitura, campo))
        if self.sentidos[ident]["especie"] == "evento":
            return 1.0 if leitura.disparou else 0.0
        return leitura.valor

    def _ler_entrada(self, ident: str) -> float:
        entrada = self.receita.secao("entradas").get(ident, {})
        valor = self.opcoes.get(ident, entrada.get("padrao", 0.0))  # (noqa-acento)
        return float(valor) if isinstance(valor, (int, float)) else 0.0

    def _avaliar(self, caminho: tuple[str | int, ...]) -> float:
        return expressao.avaliar(self.receita.expressoes[caminho], self._ler_nome,
                                 self._ler_entrada)

    def _calcular(self, t_ms: float) -> None:
        derivados = self.receita.secao("derivados")
        estados = self.receita.secao("estados")
        for ident in self.receita.ordem:
            if ident in self.acumuladores:
                quantos = sum(1 for e in derivados[ident]["acumula"]["sobe_com"]
                              if self.leituras[e].disparou)
                self.valores[ident] = self.acumuladores[ident].atualizar(t_ms, quantos)
            elif ident in derivados:
                self.valores[ident] = self._avaliar(("derivados", ident, "expr"))
            else:
                caminho = ("estados", ident, "quando")
                liga = self._avaliar(caminho) != 0.0
                continua = liga
                histerese = float(estados[ident].get("histerese", 0))
                topo = expressao.comparacao_do_topo(self.receita.expressoes[caminho])
                if histerese > 0 and topo is not None:
                    esquerda = expressao.avaliar(topo.esquerda, self._ler_nome, self._ler_entrada)
                    direita = expressao.avaliar(topo.direita, self._ler_nome, self._ler_entrada)
                    continua = continua_com_histerese(topo.op, esquerda, direita, histerese)
                ligado = self.estados[ident].atualizar(t_ms, liga, continua)
                self.valores[ident] = 1.0 if ligado else 0.0

    def _alvos(self, regra: dict[str, Any], indice: int) -> tuple[str, ...]:
        para = regra.get("para", "todos")
        if para == "todos":
            return tuple(sorted(self.jogadores))
        if para == "quem_levou":
            no = self.receita.expressoes[("regras", indice, "quando")]
            quem: set[str] = set()
            for nome in expressao.nomes(no):
                leitura = self.leituras.get(nome)
                if leitura is not None and leitura.disparou and leitura.uniq is not None:
                    quem.add(leitura.uniq)
            return tuple(sorted(quem & self.jogadores.keys()))
        numeros = {int(p[1:]) for p in para}
        return tuple(sorted(u for u, j in self.jogadores.items() if j in numeros))

    def _fim(self, efeito: dict[str, Any], t_ms: float, de_borda: bool) -> float | None:
        if "dura_ms" in efeito:
            return t_ms + float(efeito["dura_ms"])
        if efeito["canal"] == "haptica" and not catalogo.PADROES[efeito["padrao"]].repete:  # (noqa-acento)
            return t_ms + catalogo.PADROES[efeito["padrao"]].dura_ms  # (noqa-acento)
        if efeito["canal"] == "leds":
            return t_ms + luzes.PRAZO_MAXIMO_MS
        return t_ms + DURACAO_MINIMA_MS if de_borda else None

    def _ativar(self, indice: int, nomes: Any, t_ms: float, de_borda: bool) -> None:
        regra = self.receita.regras[indice]
        alvos = self._alvos(regra, indice)
        no = self.receita.expressoes[("regras", indice, "quando")]
        marcas = [self.leituras[n].t for n in sorted(expressao.nomes(no))
                  if n in self.leituras and self.leituras[n].disparou]
        t_do_jogo = next((m for m in marcas if m is not None), None)
        for nome in [nomes] if isinstance(nomes, str) else nomes:
            efeito = self.receita.secao("efeitos")[nome]
            self.ativas.append(Ativacao(indice, nome, alvos, t_ms,
                                        self._fim(efeito, t_ms, de_borda), t_do_jogo))

    def _rodar_as_regras(self, t_ms: float) -> None:
        for indice, regra in enumerate(self.receita.regras):
            viva = self.regras[indice]
            vale = self._avaliar(("regras", indice, "quando")) != 0.0
            if vale and not viva.valia:
                espera = float(regra.get("espera_ms", 0))
                viva.aceita = viva.disparou_em is None or t_ms - viva.disparou_em >= espera
                if viva.aceita:
                    viva.disparou_em = t_ms
                    self._ativar(indice, regra["entao"], t_ms, de_borda=False)
            elif not vale and viva.valia and viva.aceita:
                for ativa in self.ativas:
                    if ativa.regra == indice and ativa.fim_ms is None:
                        ativa.fim_ms = max(t_ms, ativa.inicio_ms + DURACAO_MINIMA_MS)
                if "senao" in regra:
                    self._ativar(indice, regra["senao"], t_ms, de_borda=True)
            viva.valia = vale

    def _numero(self, valor: Any, caminho: tuple[str | int, ...], minimo: float,
                maximo: float, padrao: float) -> float:
        if isinstance(valor, str):
            valor = self._avaliar(caminho)
        elif not isinstance(valor, (int, float)):
            valor = padrao
        return min(maximo, max(minimo, float(valor)))

    def _pedidos(self, ativa: Ativacao) -> list[Pedido]:
        efeito = self.receita.secao("efeitos")[ativa.efeito]
        canal = efeito["canal"]
        caminho = ("efeitos", ativa.efeito)
        params: dict[str, Any] = {"inicio_ms": ativa.inicio_ms}
        if canal in ("motor", "haptica"):
            forca = self._numero(efeito.get("forca", 1.0), (*caminho, "forca"), 0.0, 1.0, 1.0)
            params["forca"] = forca
            if canal == "haptica":
                params["padrao"] = efeito["padrao"]  # (noqa-acento)
                params["bpm"] = self._numero(efeito.get("bpm", catalogo.BPM_PADRAO),
                                             (*caminho, "bpm"), 30.0, 220.0, catalogo.BPM_PADRAO)
            lado = efeito.get("lado", "ambos")
            lados = ["esquerdo", "direito"] if lado == "ambos" else [lado]
        elif canal == "gatilho":
            forca = catalogo.forca_do_gatilho(efeito)
            params["trigger"] = catalogo.para_o_trigger_set(efeito)
            lados = ["esquerdo", "direito"] if efeito["lado"] == "ambos" else [
                "esquerdo" if efeito["lado"] == "l2" else "direito"]
        elif canal == "luz":
            brilho = float(efeito.get("brilho", 1.0))
            forca = catalogo.forca_da_luz(efeito["cor"], brilho)
            params.update(rgb=catalogo.rgb(efeito["cor"]), brilho=brilho)
            lados = ["-"]
        elif canal == "leds":
            forca = 1.0
            fim = ativa.fim_ms if ativa.fim_ms is not None else ativa.inicio_ms
            params.update(mascara=luzes.mascara(efeito["lado"]),
                          ate_ms=luzes.prazo(fim - ativa.inicio_ms))
            lados = ["-"]
        else:
            forca = float(efeito.get("volume", 1.0))
            params.update(som=efeito["som"], volume=forca)
            if efeito["som"] == "recorte":
                if ativa.t_do_jogo is None:
                    return []
                params["t"] = ativa.t_do_jogo
            lados = ["-"]
        prioridade = int(self.receita.regras[ativa.regra].get("prioridade", 0))
        return [Pedido(uniq, canal, lado, ativa.efeito, forca, prioridade, ativa.inicio_ms,
                       ativa.regra, params)
                for uniq in ativa.alvos if uniq in self.jogadores for lado in lados]

    def passo(self, t_ms: float) -> dict[Vaga, Pedido]:
        """Um tique: lê os eventos, calcula a cena, roda as regras e decide cada vaga."""
        for leitura in self.leituras.values():
            leitura.disparou = False
        fila, self._fila = self._fila, []
        derivados: list[universais.Derivado] = []
        for sentido in self.universais:
            derivados += sentido.tique(t_ms, self.jogadores, self.vibrando)
        for evento in fila:
            for sentido in self.universais:
                if evento.topico in sentido.origens:
                    derivados += sentido.ler(evento.topico, evento.nome, evento.uniq,
                                             evento.dados, t_ms)
        fila += [_Evento(d.topico, d.nome, d.uniq, d.dados) for d in derivados]
        for evento in fila:
            self._ler_evento(evento)
        self._calcular(t_ms)
        self._rodar_as_regras(t_ms)
        self.ativas = [a for a in self.ativas if a.fim_ms is None or t_ms < a.fim_ms]
        vencedores = decidir(p for a in self.ativas for p in self._pedidos(a))
        self.vibrando = frozenset(p.uniq for p in vencedores.values()
                                  if p.canal in ("motor", "haptica") and p.forca > 0)
        return vencedores


async def rodar(motor: Motor, saida: Saida, parar: asyncio.Event,
                relogio: Callable[[], float] = time.monotonic, hz: int = HZ) -> None:
    """O laço: um passo do motor e a saída a cada ``1/hz`` segundo, até ``parar``."""
    intervalo = 1.0 / hz
    proximo = relogio()
    while not parar.is_set():
        t_ms = relogio() * 1000.0
        await saida.aplicar(t_ms, motor.passo(t_ms))
        proximo += intervalo
        espera = proximo - relogio()
        if espera < 0:
            proximo = relogio()
            espera = 0.0
        try:
            await asyncio.wait_for(parar.wait(), espera)
        except asyncio.TimeoutError:
            pass
    await saida.soltar_tudo(relogio() * 1000.0)
