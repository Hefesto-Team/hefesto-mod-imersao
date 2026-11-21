"""O que as provas dividem: a raiz no caminho, os controles forjados e as portas de mentira."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

RECEITAS = RAIZ / "testes" / "receitas"
UM, DOIS, TRES, QUATRO = (f"aa:bb:cc:00:00:0{n}" for n in range(1, 5))
QUATRO_CONTROLES = [{"uniq": u, "jogador": j} for j, u in enumerate((UM, DOIS, TRES, QUATRO), 1)]


def vibracao_do_jogo(uniq: str, forte: int, fraco: int = 0, jogador: int = 1) -> dict[str, Any]:
    """Os dados do ``jogo.vibracao`` como a porta os entrega: os pares em ``[fraco, forte]``."""
    return {"uniq": uniq, "jogador": jogador, "pedido": [fraco, forte],
            "efetivo": [fraco, forte], "jogo": [forte, fraco], "toques": [0, 0], "t": 1.0}


class Recusa(RuntimeError):
    def __init__(self, mensagem: str, codigo: int) -> None:
        super().__init__(mensagem)
        self.codigo = codigo


class EscritasDeMentira:
    """O ``pedir`` da porta sem socket: guarda ``(instante, método, params)`` de cada escrita.

    ``com_haptica`` e ``com_som`` dizem se a porta conhece ``haptica.tocar`` e ``som.tocar``;
    sem eles, a resposta é o -32601 de método desconhecido. Com ``devolve``, o ``luz.set`` e o
    ``gatilho.set`` que levam ``ate_ms`` respondem ``devolve: true``, como a porta que devolve o
    que havia quando o prazo vence. Como no Hefesto, o ``haptica.tocar``
    de um padrão que não passou pelo ``haptica.registrar`` recusa com -32602. O registro não escreve no controle: ele
    fica em ``registros``, com o número de escritas que já havia, e não em ``escritas``.
    """

    def __init__(self, com_haptica: bool = False, com_som: bool = False,
                 devolve: bool = False) -> None:
        self.agora = 0.0
        self.devolve = devolve
        self.escritas: list[tuple[float, str, dict[str, Any]]] = []
        self.com_haptica = com_haptica
        self.com_som = com_som
        self.registrados: set[str] = set()
        self.registros: list[tuple[int, str]] = []

    async def pedir(self, metodo: str, params: dict[str, Any]) -> dict[str, Any]:
        if (metodo in ("haptica.tocar", "haptica.registrar") and not self.com_haptica) or (
                metodo == "som.tocar" and not self.com_som):
            raise Recusa(f"método desconhecido: {metodo}", -32601)
        if metodo == "haptica.registrar":
            self.registrados.add(params["id"])
            self.registros.append((len(self.escritas), params["id"]))
            return {"status": "ok"}
        if metodo == "haptica.tocar" and params["id"] not in self.registrados:
            raise Recusa(f"haptica.tocar: padrão não registrado: {params['id']}", -32602)
        self.escritas.append((self.agora, metodo, dict(params)))
        if self.devolve and metodo in ("luz.set", "gatilho.set") and "ate_ms" in params:
            return {"status": "ok", "devolve": True}
        return {"status": "ok"}

    def esquecer(self) -> None:
        self.registrados.clear()

    def de(self, metodo: str) -> list[tuple[float, dict[str, Any]]]:
        return [(t, p) for t, m, p in self.escritas if m == metodo]


class PortaDeMentira:
    """A porta das modificações do lado do Hefesto, num socket: guarda cada pedido."""

    def __init__(self, controles: list[dict[str, Any]] | None = None) -> None:
        self.controles = controles if controles is not None else [
            {"uniq": UM, "jogador": 1}, {"uniq": DOIS, "jogador": 2}]
        self.pedidos: list[tuple[str, dict[str, Any]]] = []
        self.escritores: list[asyncio.StreamWriter] = []
        self.assinados: set[str] = set()

    @property
    def metodos(self) -> list[str]:
        return [m for m, _ in self.pedidos]

    def de(self, metodo: str) -> list[dict[str, Any]]:
        return [p for m, p in self.pedidos if m == metodo]

    async def atender(self, leitor: asyncio.StreamReader, escritor: asyncio.StreamWriter) -> None:
        self.escritores.append(escritor)
        while linha := await leitor.readline():
            pedido = json.loads(linha)
            metodo, params = pedido["method"], pedido.get("params") or {}
            self.pedidos.append((metodo, params))
            erro = None
            resultado: Any = {"status": "ok"}
            if metodo == "mod.ola":
                resultado = {"id": "imersao", "api": 2, "permissoes": []}  # (noqa-acento)
            elif metodo == "controles.lista":
                resultado = {"controles": self.controles}
            elif metodo == "eventos.assinar":
                self.assinados |= set(params.get("topicos", []))
                resultado = {"assinados": params.get("topicos", [])}
            elif metodo in ("haptica.tocar", "haptica.registrar", "som.tocar"):
                erro = {"code": -32601, "message": f"método desconhecido: {metodo}"}
            resposta: dict[str, Any] = {"jsonrpc": "2.0", "id": pedido["id"]}
            resposta.update({"error": erro} if erro else {"result": resultado})
            escritor.write(json.dumps(resposta).encode() + b"\n")
            await escritor.drain()

    async def publicar(self, topico: str, nome: str, dados: dict[str, Any],
                       uniq: str | None = None) -> None:
        if topico not in self.assinados:
            return
        for escritor in self.escritores:
            escritor.write(json.dumps({"jsonrpc": "2.0", "method": "evento", "params": {
                "topico": topico, "nome": nome, "uniq": uniq, "dados": dados}}).encode() + b"\n")
            await escritor.drain()


async def ate(condicao: Any, prazo: float = 5.0) -> None:
    fim = asyncio.get_running_loop().time() + prazo
    while not condicao():
        if asyncio.get_running_loop().time() > fim:
            raise AssertionError("o prazo passou sem a condição")
        await asyncio.sleep(0.02)
