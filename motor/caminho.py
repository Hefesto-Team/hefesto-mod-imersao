"""O caminho do controle do jogo, medido ao vivo: em que canal de cada controle o jogo escreve.

O jogo pelo XInput só escreve os dois motores; pelo hidraw Sony ele escreve também a luz e o
gatilho; com a saída de áudio do controle, ele ocupa a háptica. Nada disso vem de tabela: o
:class:`Caminho` lê o que a porta já entrega (``jogo.vibracao``, ``jogo.haptica`` e
``jogo.gatilho``) e a recusa ``-32011`` que o jogo vence (a luz do jogo não tem tópico). O canal em
que o jogo escreveu nos últimos :data:`JANELA_MS` está ocupado, e nele a receita só sai quando é
mais forte que o nível do jogo; no canal livre, ela sai inteira.

A máscara do lançamento (``jogo.identidade``) diz de saída se o jogo alcança a luz e o gatilho:
pela máscara Xbox ou Nintendo, não, e a recusa nesses canais não é do jogo. O motor e a háptica
não dependem da máscara: o motor chega por qualquer uma, e a háptica pelo áudio do controle.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from motor.arbitragem import Pedido, Vaga
from sentidos.base import numero
from sentidos.rumble import nivel_do_jogo

JANELA_MS = 3000.0
SEM_BATIDA_MS = 600.0
CANAIS = ("motor", "haptica", "gatilho", "luz")
PELO_HIDRAW = frozenset({"luz", "gatilho"})
ALCANCE = {
    "dualsense": frozenset(CANAIS),
    "xbox": frozenset(CANAIS) - PELO_HIDRAW,
    "nintendo": frozenset(CANAIS) - PELO_HIDRAW,
}
LADOS = ("esquerdo", "direito")


@dataclass
class _Uso:
    nivel: float
    t_ms: float
    batida: bool
    por_recusa: bool = False


def recusa_do_jogo(dados: Any) -> bool:
    """A recusa ``-32011`` é do jogo quando ``data.vence`` diz ``jogo`` ou não diz nada."""
    if not isinstance(dados, dict) or "vence" not in dados:
        return True
    return dados["vence"] == "jogo"


class Caminho:
    """O nível que o jogo escreve em cada vaga ``(uniq, canal, lado)`` e a máscara dele."""

    def __init__(self) -> None:
        self.usos: dict[Vaga, _Uso] = {}
        self.mascaras: dict[str | None, str] = {}

    def _usou(self, vaga: Vaga, nivel: float, t_ms: float, batida: bool) -> None:
        self.usos[vaga] = _Uso(min(1.0, max(0.0, nivel)), t_ms, batida)

    def ler(self, topico: str, nome: str, uniq: str | None, dados: dict[str, Any],
            t_ms: float) -> None:
        if nome == "jogo.fechou":
            self.usos.clear()
            self.mascaras.clear()
            return
        if topico == "jogo.identidade":
            mascara = dados.get("mascara")
            if isinstance(mascara, str) and mascara.lower() in ALCANCE:
                self.mascaras[uniq] = mascara.lower()
            return
        if uniq is None:
            return
        if topico == "jogo.vibracao":
            par = nivel_do_jogo(dados)
            if par is not None:
                for lado, nivel in zip(LADOS, par):
                    self._usou((uniq, "motor", lado), nivel, t_ms, batida=True)
        elif topico == "jogo.haptica":
            par = dados.get("intensidade")
            if isinstance(par, list) and len(par) == len(LADOS):
                for lado, valor in zip(LADOS, par):
                    intensidade = numero(valor)
                    if intensidade is not None:
                        self._usou((uniq, "haptica", lado), intensidade, t_ms, batida=True)
        elif topico == "jogo.gatilho":
            qual = dados.get("lado")
            forca = 0.0 if dados.get("modo") == "desligado" else numero(dados.get("forca"))
            if isinstance(qual, str) and qual in LADOS and forca is not None:
                self._usou((uniq, "gatilho", qual), forca, t_ms, batida=False)

    def alcanca(self, uniq: str, canal: str) -> bool:
        """Se o jogo pode escrever no canal pela máscara; sem máscara, pode."""
        mascara = self.mascaras.get(uniq, self.mascaras.get(None))
        return mascara is None or canal in ALCANCE[mascara]

    def recusou(self, vaga: Vaga, forca: float, dados: Any, t_ms: float) -> None:
        """A porta recusou o pedido de ``forca``: o jogo vence ali com pelo menos essa força."""
        uniq, canal, _ = vaga
        if canal not in CANAIS or not recusa_do_jogo(dados) or not self.alcanca(uniq, canal):
            return
        atual = self.nivel(vaga, t_ms)
        self.usos[vaga] = _Uso(max(forca, atual or 0.0), t_ms, batida=False, por_recusa=True)

    def nivel(self, vaga: Vaga, t_ms: float) -> float | None:
        """O nível do jogo na vaga, ou ``None`` quando o jogo não a ocupa."""
        uso = self.usos.get(vaga)
        if uso is None or t_ms - uso.t_ms > JANELA_MS or not self.alcanca(vaga[0], vaga[1]):
            return None
        if uso.batida and t_ms - uso.t_ms > SEM_BATIDA_MS:
            return 0.0
        return uso.nivel

    def ocupadas(self, uniq: str, t_ms: float) -> set[str]:
        """Os canais do controle em que o jogo escreveu na janela: o caminho medido."""
        return {canal for (u, canal, lado) in self.usos
                if u == uniq and self.nivel((u, canal, lado), t_ms) is not None}

    def filtrar(self, vencedores: dict[Vaga, Pedido], t_ms: float,
                haptica_pelo_motor: bool = False) -> dict[Vaga, Pedido]:
        """Os vencedores que passam do jogo: no canal ocupado, só o mais forte que ele."""
        return {vaga: pedido for vaga, pedido in vencedores.items()
                if self._passa(pedido, t_ms, haptica_pelo_motor)}

    def _passa(self, pedido: Pedido, t_ms: float, haptica_pelo_motor: bool) -> bool:
        if pedido.canal not in CANAIS:
            return True
        niveis: Iterable[float | None] = [self.nivel(pedido.vaga, t_ms)]
        if pedido.canal == "haptica" and haptica_pelo_motor:
            niveis = [*niveis, self.nivel((pedido.uniq, "motor", pedido.lado), t_ms)]
        ocupado = [n for n in niveis if n is not None]
        return not ocupado or pedido.forca > max(ocupado)
