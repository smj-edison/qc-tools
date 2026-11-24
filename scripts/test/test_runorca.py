import re
from pathlib import Path

import pytest


def test_reports_nprocs_and_mem_from_pal_block(run_script, templates_dir, tmp_path):
    src = templates_dir / "wB97M IN template.inp"
    dest = tmp_path / "mol.inp"
    dest.write_text(src.read_text())

    result = run_script("runorca", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "--ntasks-per-node=24" in result.stdout
    assert "--qos=test" in result.stdout
    match = re.search(r"--mem=([\d.]+)MB", result.stdout)
    assert match, result.stdout
    assert float(match.group(1)) == pytest.approx(2000 * 24 * 1.1)


def test_reports_nprocs_and_mem_for_ts_template(run_script, templates_dir, tmp_path):
    src = templates_dir / "wB97M TS template.inp"
    dest = tmp_path / "ts.inp"
    dest.write_text(src.read_text())

    result = run_script("runorca", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "--ntasks-per-node=24" in result.stdout
    match = re.search(r"--mem=([\d.]+)MB", result.stdout)
    assert match, result.stdout
    assert float(match.group(1)) == pytest.approx(2000 * 24 * 1.1)


def test_rejects_wrong_extension(run_script, tmp_path):
    dest = tmp_path / "mol.gjf"
    dest.write_text("junk")

    result = run_script("runorca", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode != 0
    assert "not a .inp file" in result.stderr


@pytest.mark.parametrize(
    "prefix_args, expected",
    [
        ([], Path.home() / "bin/orca_6_1_1_linux_x86-64_shared_openmpi418_avx2/orca"),
        (["--prefix", "/opt/orca/"], "/opt/orca/orca"),
        (["-p", "~/my-orca"], Path.home() / "my-orca/orca"),
        (["-p", "/opt/my orca"], "'/opt/my orca/orca'"),
    ],
)
def test_orca_prefix(run_script, tmp_path, prefix_args, expected):
    dest = tmp_path / "mol.inp"
    dest.write_text("! SP")

    result = run_script("runorca", dest, "-t", "1-00:00:00", "-q", "test", *prefix_args)

    assert result.returncode == 0, result.stderr
    assert f"\n{expected} '{dest}' > " in result.stdout


def test_relative_orca_prefix_is_made_absolute(run_script, tmp_path):
    dest = tmp_path / "mol.inp"
    dest.write_text("! SP")

    result = run_script("runorca", dest, "-t", "1-00:00:00", "-q", "test", "-p", ".")

    assert result.returncode == 0, result.stderr
    assert f"\n{tmp_path / 'orca'} '" in result.stdout
