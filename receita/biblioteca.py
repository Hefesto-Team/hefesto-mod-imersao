"""Qual receita vale agora: a do jogo aberto, pela chave dele, ou o universal.

As receitas moram em três lugares, nesta ordem de precedência: as de quem joga
(``$HEFESTO_MOD_DADOS/receitas/*.json``, e o ``receita.json`` de antes), as estudadas que vêm com a
extensão (``receitas/estudadas/*.json``) e as da comunidade, baixadas e conferidas
(``$HEFESTO_MOD_DADOS/comunidade/*.json``). Cada arquivo diz o jogo dele em ``jogo.chave``; o nome do
arquivo não conta. A receita de quem joga sem ``jogo.chave`` vale em todo jogo sem receita própria,
como valia o ``receita.json`` antes de existir receita por jogo. Sem nenhuma, ou com «Universal» na
opção ``receita``, vale o universal. A receita recusada vai ao diário com a linha do erro e não
conta.

O arquivo validado (ou recusado) se guarda pelo caminho, o instante de modificação e o tamanho: a
escolha de uma receita não relê nem valida de novo o que não mudou no disco, e o arquivo que muda
é lido outra vez. A recusa vai ao diário uma vez por versão do arquivo.
"""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

from receita.formato import Receita, ReceitaRecusada, ler_receita

PASTA_DE_QUEM_JOGA = "receitas"
PASTA_DA_COMUNIDADE = "comunidade"
ARQUIVO_DE_ANTES = "receita.json"
ORIGENS = ("sua", "estudada", "comunidade")
ROTULOS = {
    "sua": "Sua receita",
    "estudada": "Receita estudada",
    "comunidade": "Receita da comunidade",
    "universal": "Universal",
}
PELO_JOGO = "Pelo jogo"
UNIVERSAL_SEMPRE = "Universal"
ESCOLHAS_DA_RECEITA = (PELO_JOGO, UNIVERSAL_SEMPRE)


@dataclass(frozen=True)
class Escolhida:
    """A receita que vale, de onde ela veio e o arquivo dela (``None`` no universal)."""

    receita: Receita
    origem: str
    arquivo: Path | None = None

    @property
    def rotulo(self) -> str:
        return ROTULOS[self.origem]

    @property
    def marca(self) -> tuple[str, str | None]:
        return (self.origem, str(self.arquivo) if self.arquivo else None)


class Biblioteca:
    """As pastas de receitas e o universal; :meth:`para` escolhe a do jogo."""

    def __init__(self, estudadas: Path, dados: Path | None, universal: Callable[[], Receita],
                 diario: Callable[[str], None] | None = None) -> None:
        self.estudadas = estudadas
        self.dados = dados
        self._universal = universal
        self._diario = diario or (lambda _frase: None)
        self._guardadas: dict[Path, tuple[tuple[int, int], Receita | None]] = {}

    def pastas(self) -> dict[str, list[Path]]:
        """Os arquivos de cada origem, em ordem de nome."""
        sua: list[Path] = []
        comunidade: list[Path] = []
        if self.dados is not None:
            antes = self.dados / ARQUIVO_DE_ANTES
            sua = _jsons(self.dados / PASTA_DE_QUEM_JOGA) + ([antes] if antes.is_file() else [])
            comunidade = _jsons(self.dados / PASTA_DA_COMUNIDADE)
        return {"sua": sua, "estudada": _jsons(self.estudadas), "comunidade": comunidade}

    def _lidas(self, origem: str, arquivos: list[Path]) -> Iterator[tuple[Path, Receita]]:
        for arquivo in arquivos:
            try:
                estado = arquivo.stat()
                marca = (estado.st_mtime_ns, estado.st_size)
                guardada = self._guardadas.get(arquivo)
                if guardada is not None and guardada[0] == marca:
                    receita = guardada[1]
                else:
                    receita = None
                    try:
                        receita = ler_receita(arquivo.read_bytes())
                    except ReceitaRecusada as exc:
                        self._diario(f"a receita {arquivo} foi recusada e não vale:\n{exc}")
                    self._guardadas[arquivo] = (marca, receita)
            except OSError:
                continue
            if receita is not None:
                yield arquivo, receita

    def para(self, chave: str | None, escolha: str = PELO_JOGO) -> Escolhida:
        """A receita do jogo ``chave`` (``None`` fora de jogo) pela precedência das origens."""
        if escolha != UNIVERSAL_SEMPRE:
            pastas = self.pastas()
            vivos = {arquivo for arquivos in pastas.values() for arquivo in arquivos}
            self._guardadas = {k: v for k, v in self._guardadas.items() if k in vivos}
            geral: Escolhida | None = None
            for origem in ORIGENS:
                for arquivo, receita in self._lidas(origem, pastas[origem]):
                    dela = receita.dados.get("jogo", {}).get("chave")
                    if chave is not None and dela == chave:
                        return Escolhida(receita, origem, arquivo)
                    if dela is None and origem == "sua" and geral is None:
                        geral = Escolhida(receita, origem, arquivo)
            if geral is not None:
                return geral
        return Escolhida(self._universal(), "universal")


def _jsons(pasta: Path) -> list[Path]:
    try:
        with os.scandir(pasta) as itens:
            return sorted(Path(i.path) for i in itens if i.name.endswith(".json") and i.is_file())
    except OSError:
        return []
