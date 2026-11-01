"""O ``ruff check .`` e o ``mypy .`` da extensão fecham sem achado, com a configuração da raiz e
as ferramentas da ``.venv`` que roda as provas."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from apoio import RAIZ


def _ferramenta(nome: str) -> str:
    vizinha = Path(sys.executable).with_name(nome)
    caminho = str(vizinha) if vizinha.exists() else shutil.which(nome)
    if caminho is None:
        pytest.skip(f"sem o {nome} nesta máquina")
    return caminho


def _rodar(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=RAIZ, capture_output=True, text=True, timeout=300,
                          check=False)


def test_o_ruff_fecha_limpo() -> None:
    feito = _rodar(_ferramenta("ruff"), "check", "--no-cache", "--output-format", "concise", ".")
    assert feito.returncode == 0, f"o ruff achou:\n{feito.stdout}{feito.stderr}"
    assert "warning" not in feito.stderr, f"o ruff avisou:\n{feito.stderr}"


def test_o_mypy_fecha_limpo(tmp_path: Path) -> None:
    _ferramenta("mypy")
    feito = _rodar(sys.executable, "-m", "mypy", "--cache-dir", str(tmp_path / "cache"), ".")
    assert feito.returncode == 0, f"o mypy achou:\n{feito.stdout}{feito.stderr}"
    assert "Success: no issues found" in feito.stdout, feito.stdout
