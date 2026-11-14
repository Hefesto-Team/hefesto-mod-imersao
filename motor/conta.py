"""A conta do minuto para o diário: por controle, os efeitos que tocaram em cada canal e os que não
tocaram, pelo motivo.

Um efeito conta uma vez, quando começa (o controle, o canal, o efeito e o instante em que começou).
Toca quando vence a vaga, passa do jogo e a porta não o recusa naquele tique; não toca quando o jogo
escreve mais forte no canal (``jogo_mais_forte``, medido pela extensão) ou quando a porta recusa,
pelo motivo que ela devolve. O resumo sai só no minuto em que houve jogo, numa linha, com os
controles separados pelo nome (a cor do plástico) e nunca pelo ``uniq``.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from motor.arbitragem import Pedido, Vaga

JOGO_MAIS_FORTE = "jogo_mais_forte"
TETO_DA_LINHA = 480
TETO_DE_RESUMOS = 1440
SEM_NOME = "Controle fora"
NOMES_DOS_CANAIS = {
    "haptica": "vibração fina", "motor": "motores", "gatilho": "gatilhos", "luz": "barra de luz",
    "leds": "luzes de jogador", "som": "alto-falante", "mira": "mira",
}
CANAL_DA_CHAVE = {"vibracao": "motor"}

Identidade = tuple[str, str, str, float]


def _identidade(pedido: Pedido) -> Identidade:
    return (pedido.uniq, pedido.canal, pedido.efeito, pedido.inicio_ms)


class ContaDoMinuto:
    """Os números de um minuto; :meth:`fechar` devolve a linha e zera a conta."""

    def __init__(self) -> None:
        self.tocados: Counter[tuple[str, str]] = Counter()
        self.recusas: Counter[tuple[str, str]] = Counter()
        self.houve_jogo = False
        self.resumos = 0
        self._tocou: set[Identidade] = set()
        self._cedeu: set[Identidade] = set()

    def tique(self, vencedores: Mapping[Vaga, Pedido], cedidos: Mapping[Vaga, Pedido],
              recusas: Iterable[tuple[str, str, str]], com_jogo: bool) -> None:
        """Um tique da saída: ``recusas`` são ``(uniq, canal da escrita, motivo)`` da porta."""
        self.houve_jogo |= com_jogo
        recusados: set[tuple[str, str]] = set()
        for uniq, canal, motivo in recusas:
            self.recusas[(uniq, motivo)] += 1
            recusados.add((uniq, CANAL_DA_CHAVE.get(canal, canal)))
        vivos: set[Identidade] = set()
        for pedido in vencedores.values():
            if pedido.forca <= 0:
                continue
            ident = _identidade(pedido)
            vivos.add(ident)
            if ident in self._tocou or ident in self._cedeu:
                continue
            if (pedido.uniq, pedido.canal) in recusados:
                self._cedeu.add(ident)
            else:
                self._tocou.add(ident)
                self.tocados[(pedido.uniq, pedido.canal)] += 1
        for pedido in cedidos.values():
            ident = _identidade(pedido)
            vivos.add(ident)
            if pedido.forca > 0 and ident not in self._cedeu and ident not in self._tocou:
                self._cedeu.add(ident)
                self.recusas[(pedido.uniq, JOGO_MAIS_FORTE)] += 1
        self._tocou &= vivos
        self._cedeu &= vivos

    def fechar(self, hora: str, nomes: Mapping[str, str]) -> str | None:
        """A linha do minuto que acabou, ou ``None`` no minuto sem jogo e depois do teto."""
        houve, self.houve_jogo = self.houve_jogo, False
        tocados, recusas = self.tocados, self.recusas
        self.tocados, self.recusas = Counter(), Counter()
        if not houve or self.resumos >= TETO_DE_RESUMOS:
            return None
        self.resumos += 1
        uniqs = sorted({u for u, _ in tocados} | {u for u, _ in recusas} | set(nomes),
                       key=lambda u: (u not in nomes, list(nomes).index(u) if u in nomes else 0))
        partes = [self._do_controle(nomes.get(u, SEM_NOME), u, tocados, recusas) for u in uniqs]
        linha = f"resumo do minuto {hora}: " + (" | ".join(partes) if partes else "nenhum controle")
        if self.resumos == TETO_DE_RESUMOS:
            linha += " | o resumo para aqui, no teto de linhas"
        return linha[:TETO_DA_LINHA]

    @staticmethod
    def _do_controle(nome: str, uniq: str, tocados: Counter[tuple[str, str]],
                     recusas: Counter[tuple[str, str]]) -> str:
        tocou = ", ".join(f"{NOMES_DOS_CANAIS.get(c, c)} {n}" for (u, c), n in sorted(
            tocados.items()) if u == uniq)
        nao = ", ".join(f"{m} {n}" for (u, m), n in sorted(recusas.items()) if u == uniq)
        texto = f"{nome} tocou {tocou or 'nada'}"
        return f"{texto}; não tocou: {nao}" if nao else texto
