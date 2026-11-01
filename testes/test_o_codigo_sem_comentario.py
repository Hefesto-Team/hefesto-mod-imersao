"""O código da extensão não leva comentário: só as diretivas das ferramentas e as docstrings."""
from __future__ import annotations

import io
import re
import tokenize

from apoio import RAIZ

DIRETIVA = re.compile(r"^#\s*(noqa\b|type:|\(noqa-acento\)|noqa-acento)")


def _fontes(sufixo: str) -> list:
    return sorted(p for p in RAIZ.rglob(f"*{sufixo}") if ".git" not in p.parts)


def test_nenhum_comentario_no_python() -> None:
    achados = []
    for arquivo in _fontes(".py"):
        fichas = tokenize.generate_tokens(io.StringIO(arquivo.read_text("utf-8")).readline)
        for ficha in fichas:
            if ficha.type == tokenize.COMMENT and not DIRETIVA.match(ficha.string):
                achados.append(f"{arquivo.relative_to(RAIZ)}:{ficha.start[0]}: {ficha.string}")
    assert not achados, "\n".join(achados)


def test_nenhum_comentario_no_shell() -> None:
    achados = []
    for arquivo in _fontes(".sh"):
        for numero, linha in enumerate(arquivo.read_text("utf-8").splitlines(), 1):
            if linha.lstrip().startswith("#") and not (numero == 1 and linha.startswith("#!")):
                achados.append(f"{arquivo.relative_to(RAIZ)}:{numero}: {linha.strip()}")
    assert not achados, "\n".join(achados)
