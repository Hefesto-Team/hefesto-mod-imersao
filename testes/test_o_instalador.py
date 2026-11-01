"""O ``install.sh`` e o ``uninstall.sh`` com um Hefesto de mentira: nenhum toca a casa de verdade."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from apoio import RAIZ


@pytest.fixture
def casa(tmp_path: Path) -> Path:
    (tmp_path / "bin").mkdir()
    (tmp_path / "home").mkdir()
    return tmp_path


def _cli(casa: Path, saida: str = "", rc: int = 0) -> Path:
    cli = casa / "bin" / "hefesto-de-mentira"
    cli.write_text("#!/usr/bin/env bash\n"
                   f'printf "%s\\n" "$@" > "{casa}/chamada"\n'
                   f"printf '%s\\n' '{saida}'\n"
                   f"exit {rc}\n", encoding="utf-8")
    cli.chmod(0o755)
    return cli


def _rodar(casa: Path, roteiro: str, *args: str, cli: Path | str) -> subprocess.CompletedProcess[str]:
    ambiente = {"PATH": f"{casa / 'bin'}:/usr/bin:/bin", "HOME": str(casa / "home"),
                "HEFESTO_CLI": str(cli)}
    return subprocess.run(["bash", str(RAIZ / roteiro), *args], env=ambiente,
                          capture_output=True, text=True, timeout=30, check=False)


def _chamada(casa: Path) -> list[str]:
    return (casa / "chamada").read_text(encoding="utf-8").splitlines()


def test_o_install_entrega_a_pasta_ao_hefesto_e_o_yes_vira_o_sim(casa: Path) -> None:
    cli = _cli(casa)
    feito = _rodar(casa, "install.sh", "--yes", cli=cli)
    assert feito.returncode == 0, feito.stderr
    assert _chamada(casa) == ["mod", "instalar", str(RAIZ), "--sim"]
    assert _rodar(casa, "install.sh", cli=cli).returncode == 0
    assert _chamada(casa) == ["mod", "instalar", str(RAIZ)]


def test_o_install_recusa_opcao_desconhecida_sudo_e_hefesto_ausente(casa: Path) -> None:
    cli = _cli(casa)
    assert _rodar(casa, "install.sh", "--forca", cli=cli).returncode == 2
    sem = _rodar(casa, "install.sh", cli=casa / "nao-existe")
    assert sem.returncode == 1 and "não está instalado" in sem.stderr
    ambiente = {"PATH": "/usr/bin:/bin", "HOME": str(casa / "home"), "SUDO_USER": "alguem",
                "HEFESTO_CLI": str(cli)}
    for roteiro in ("install.sh", "uninstall.sh"):
        feito = subprocess.run(["bash", str(RAIZ / roteiro)], env=ambiente, capture_output=True,
                               text=True, timeout=30, check=False)
        assert feito.returncode == 1 and "sem sudo" in feito.stderr
    assert not (casa / "chamada").exists()


def test_o_uninstall_remove_e_e_idempotente(casa: Path) -> None:
    feito = _rodar(casa, "uninstall.sh", cli=_cli(casa, "«imersao» removida"))
    assert feito.returncode == 0 and _chamada(casa) == ["mod", "remover", "imersao"]
    ausente = _rodar(casa, "uninstall.sh", cli=_cli(casa, "«imersao» não está instalada.", 1))
    assert ausente.returncode == 0
    quebrado = _rodar(casa, "uninstall.sh", cli=_cli(casa, "«imersao» não saiu inteira", 1))
    assert quebrado.returncode == 1
    assert _rodar(casa, "uninstall.sh", cli=casa / "nao-existe").returncode == 0
    assert os.listdir(casa / "home") == []
