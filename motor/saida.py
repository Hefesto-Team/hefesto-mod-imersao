"""A saída pela porta das modificações: só o que muda, renovado a tempo e sob o teto do tato vivo.

Cada tique recebe o vencedor de cada vaga e escreve a diferença: ``vibracao.set`` (o motor
esquerdo é o ``forte``, o direito o ``fraco``, e o par se renova antes dos 3 s da porta),
``gatilho.set`` com os nomes do ``trigger.set``, ``luz.set``, ``haptica.tocar`` e ``som.tocar``.
O teto é o do tato vivo, 12 escritas por segundo em cada controle e 40 no total: o que passa
espera o tique seguinte, e o valor mais novo é o que sai. Quando a porta não conhece
``haptica.tocar``, o padrão cai no motor, pelo envelope.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from motor import efeitos as catalogo
from motor.arbitragem import Pedido, Vaga

TETO_POR_CONTROLE = 12
TETO_TOTAL = 40
JANELA_MS = 1000.0
RENOVA_MS = 2500.0
ATE_MS_DA_HAPTICA = 3000
METODO_DESCONHECIDO = -32601

Pedir = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
Chave = tuple[str, str, str]


class Saida:
    """O que já foi escrito em cada controle, e a conta do teto."""

    def __init__(self, pedir: Pedir, diario: Callable[[str], None] | None = None) -> None:
        self._pedir = pedir
        self._diario = diario or (lambda _frase: None)
        self.escrito: dict[Chave, tuple[float, dict[str, Any]]] = {}
        self.janela: deque[tuple[float, str]] = deque()
        self.sem_haptica = False
        self.sem_som = False
        self._sons_tocados: set[tuple[str, str, float]] = set()

    def _cabe(self, t_ms: float, uniq: str) -> bool:
        while self.janela and t_ms - self.janela[0][0] >= JANELA_MS:
            self.janela.popleft()
        no_controle = sum(1 for _, u in self.janela if u == uniq)
        return len(self.janela) < TETO_TOTAL and no_controle < TETO_POR_CONTROLE

    async def _escrever(self, t_ms: float, chave: Chave, metodo: str,
                        params: dict[str, Any], zero: bool = False) -> bool:
        uniq = chave[0]
        if not zero and not self._cabe(t_ms, uniq):
            return False
        self.janela.append((t_ms, uniq))
        self.escrito[chave] = (t_ms, params)
        try:
            await self._pedir(metodo, params)
        except Exception as exc:
            codigo = getattr(exc, "codigo", None)
            if codigo == METODO_DESCONHECIDO and metodo == "haptica.tocar":
                self.sem_haptica = True
                self._diario("a porta não toca háptica: o padrão segue pelo motor")
                del self.escrito[chave]
                return False
            if codigo == METODO_DESCONHECIDO and metodo == "som.tocar":
                self.sem_som = True
                self._diario("a porta não toca som: o efeito de som fica calado")
                return False
            self._diario(f"{metodo} recusado: {exc}")
        return True

    def _desejado(self, t_ms: float, vencedores: dict[Vaga, Pedido]
                  ) -> dict[Chave, tuple[str, dict[str, Any], bool]]:
        desejo: dict[Chave, tuple[str, dict[str, Any], bool]] = {}
        motores: dict[str, dict[str, float]] = {}
        for (uniq, canal, lado), pedido in sorted(vencedores.items()):
            p = pedido.params
            if canal == "motor" or (canal == "haptica" and self.sem_haptica):
                forca = p["forca"]
                if canal == "haptica":
                    forca *= catalogo.envelope(p["padrao"], t_ms - p["inicio_ms"], p["bpm"])
                atual = motores.setdefault(uniq, {"esquerdo": 0.0, "direito": 0.0})
                atual[lado] = max(atual[lado], forca)
            elif canal == "haptica":
                desejo[(uniq, "haptica", lado)] = ("haptica.tocar", {
                    "uniq": uniq, "id": p["padrao"], "forca": round(p["forca"], 3),
                    "bpm": round(p["bpm"]), "lado": lado, "ate_ms": ATE_MS_DA_HAPTICA}, False)
            elif canal == "gatilho":
                nome, valores = p["trigger"]
                desejo[(uniq, "gatilho", lado)] = ("gatilho.set", {
                    "uniq": uniq, "lado": lado, "modo": nome, "params": valores}, False)
            elif canal == "luz":
                desejo[(uniq, "luz", "-")] = ("luz.set", {
                    "uniq": uniq, "rgb": p["rgb"], "brilho": p["brilho"]}, False)
            elif canal == "som":
                desejo[(uniq, "som", "-")] = ("som.tocar", {
                    "uniq": uniq, "som": p["som"], "volume": p["volume"],
                    "inicio_ms": p["inicio_ms"]}, False)
        for uniq, lados in motores.items():
            forte, fraco = round(lados["esquerdo"] * 255), round(lados["direito"] * 255)
            if forte or fraco:
                desejo[(uniq, "vibracao", "-")] = ("vibracao.set", {
                    "uniq": uniq, "fraco": fraco, "forte": forte}, False)
        for chave, (_, params) in self.escrito.items():
            if chave in desejo:
                continue
            uniq, canal, lado = chave
            if canal == "vibracao" and (params["fraco"] or params["forte"]):
                desejo[chave] = ("vibracao.set", {"uniq": uniq, "fraco": 0, "forte": 0}, True)
            elif canal == "gatilho" and params["modo"] != "Off":
                desejo[chave] = ("gatilho.set", {"uniq": uniq, "lado": lado, "modo": "Off",
                                                 "params": []}, True)
            elif canal == "haptica" and params["forca"]:
                desejo[chave] = ("haptica.tocar", {**params, "forca": 0.0, "ate_ms": 0}, True)
        return desejo

    async def aplicar(self, t_ms: float, vencedores: dict[Vaga, Pedido]) -> None:
        """Escreve o que mudou desde o tique anterior, sob o teto."""
        desejo = self._desejado(t_ms, vencedores)
        if self.sem_haptica is False and any(m == "haptica.tocar" for m, _, _ in desejo.values()):
            for chave in sorted(desejo):
                metodo, params, zero = desejo[chave]
                if metodo == "haptica.tocar" and not await self._tocar(t_ms, chave, params, zero):
                    break
            if self.sem_haptica:
                desejo = self._desejado(t_ms, vencedores)
        vivos: set[tuple[str, str, float]] = set()
        for chave in sorted(desejo):
            metodo, params, zero = desejo[chave]
            if metodo == "haptica.tocar":
                continue
            if metodo == "som.tocar":
                marca = (chave[0], params["som"], params.pop("inicio_ms"))
                vivos.add(marca)
                if self.sem_som or marca in self._sons_tocados:
                    continue
                if await self._escrever(t_ms, chave, metodo, params):
                    self._sons_tocados.add(marca)
                continue
            antes = self.escrito.get(chave)
            vence = metodo == "vibracao.set" and antes is not None and not zero and (
                t_ms - antes[0] >= RENOVA_MS)
            if antes is not None and antes[1] == params and not vence:
                continue
            await self._escrever(t_ms, chave, metodo, params, zero)
        self._sons_tocados &= vivos

    async def _tocar(self, t_ms: float, chave: Chave, params: dict[str, Any], zero: bool) -> bool:
        antes = self.escrito.get(chave)
        vence = antes is not None and not zero and t_ms - antes[0] >= RENOVA_MS
        if antes is not None and antes[1] == params and not vence:
            return True
        await self._escrever(t_ms, chave, "haptica.tocar", params, zero)
        return not self.sem_haptica

    async def soltar_tudo(self, t_ms: float) -> None:
        """O zero em tudo que ficou escrito: a extensão que sai não deixa o controle vibrando."""
        await self.aplicar(t_ms, {})
