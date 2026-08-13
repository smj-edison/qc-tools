import shutil


def test_reports_nprocs_mem_and_qos_in_job_script(run_script, templates_dir, tmp_path):
    src = templates_dir / "B3LYP IN template.gjf"
    dest = tmp_path / "mol.gjf"
    dest.write_text(src.read_text().replace("BAD_CHECKPOINT_NAME", "mol.chk"))

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "--ntasks-per-node=24" in result.stdout
    assert "--mem=72000MB" in result.stdout  # 48GB -> 48000MB, *1.5 safety margin
    assert "--qos=test" in result.stdout
    assert "differs from job file name" not in result.stdout


def test_warns_on_mismatched_chk_name(run_script, templates_dir, tmp_path):
    src = templates_dir / "B3LYP IN template.gjf"
    dest = tmp_path / "mol.gjf"
    shutil.copy(src, dest)  # keeps the placeholder %chk=BAD_CHECKPOINT_NAME

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "Using checkpoint BAD_CHECKPOINT_NAME" in result.stdout
    assert "differs from job file name, " + str(dest) in result.stdout


def test_rejects_missing_file(run_script, tmp_path):
    result = run_script("rung16", tmp_path / "nope.gjf", "-t", "1-00:00:00", "-q", "test")

    assert result.returncode != 0
    assert "does not exist" in result.stderr


def test_rejects_wrong_extension(run_script, tmp_path):
    dest = tmp_path / "mol.txt"
    dest.write_text("junk")

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode != 0
    assert "not a .gjf or .com file" in result.stderr


def test_no_warning_without_link_sections(run_script, templates_dir, tmp_path):
    src = templates_dir / "B3LYP IN template.gjf"
    dest = tmp_path / "mol.gjf"
    dest.write_text(src.read_text().replace("BAD_CHECKPOINT_NAME", "mol.chk"))

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "Warning: %nprocshared" not in result.stdout
    assert "Warning: %mem" not in result.stdout


def test_no_warning_when_link_sections_match(run_script, templates_dir, tmp_path):
    src = templates_dir / "B3LYP TS template.gjf"
    dest = tmp_path / "ts.gjf"
    dest.write_text(src.read_text().replace("BAD_CHECKPOINT_NAME", "ts.chk"))

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "Warning: %nprocshared" not in result.stdout
    assert "Warning: %mem" not in result.stdout


def test_warns_on_mismatched_link_section_resources(run_script, tmp_path):
    dest = tmp_path / "mismatch.gjf"
    dest.write_text(
        "%nprocshared=24\n"
        "%mem=48GB\n"
        "%chk=mismatch.chk\n"
        "#opt B3LYP/def2tzvp\n"
        "\n"
        "Untitled\n"
        "\n"
        "1 1\n"
        "C 0.0 0.0 0.0\n"
        "\n"
        "--link1--\n"
        "%nprocshared=48\n"
        "%mem=96GB\n"
        "%chk=mismatch.chk\n"
        "#opt=(calcfc,ts) freq B3LYP/def2tzvp geom=allchk\n"
        "\n"
    )

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "Warning: %nprocshared differs between link sections: [24, 48]" in result.stdout
    assert "Warning: %mem differs between link sections (in MB): [48000, 96000]" in result.stdout


def test_rejects_missing_mem(run_script, tmp_path):
    dest = tmp_path / "missing.gjf"
    dest.write_text(
        "%nprocshared=24\n"
        "%chk=missing.chk\n"
        "#opt B3LYP/def2tzvp\n"
        "\n"
        "Untitled\n"
        "\n"
        "1 1\n"
        "C 0.0 0.0 0.0\n"
        "\n"
    )

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode != 0
    assert "No %mem line found" in result.stderr


def test_rejects_duplicate_mem_in_same_link_section(run_script, tmp_path):
    dest = tmp_path / "dupe.gjf"
    dest.write_text(
        "%nprocshared=24\n"
        "%mem=48GB\n"
        "%mem=64GB\n"
        "%chk=dupe.chk\n"
        "#opt B3LYP/def2tzvp\n"
        "\n"
        "Untitled\n"
        "\n"
        "1 1\n"
        "C 0.0 0.0 0.0\n"
        "\n"
    )

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode != 0
    assert "Multiple %mem lines found in the same link section" in result.stderr


def test_rejects_missing_nprocshared(run_script, tmp_path):
    dest = tmp_path / "missing.gjf"
    dest.write_text(
        "%mem=48GB\n"
        "%chk=missing.chk\n"
        "#opt B3LYP/def2tzvp\n"
        "\n"
        "Untitled\n"
        "\n"
        "1 1\n"
        "C 0.0 0.0 0.0\n"
        "\n"
    )

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode != 0
    assert "No %nprocshared line found" in result.stderr


def test_warns_and_fixes_missing_trailing_blank_line(run_script, tmp_path):
    dest = tmp_path / "mol.gjf"
    dest.write_text(
        "%nprocshared=24\n"
        "%mem=48GB\n"
        "%chk=mol.chk\n"
        "#opt B3LYP/def2tzvp\n"
        "\n"
        "Untitled\n"
        "\n"
        "1 1\n"
        "C 0.0 0.0 0.0\n"
    )  # note: no trailing blank line

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert f"Warning: {dest} did not end with a blank line" in result.stdout
    assert dest.read_text().endswith("\n\n")


def test_no_warning_when_trailing_blank_line_present(run_script, tmp_path):
    dest = tmp_path / "mol.gjf"
    dest.write_text(
        "%nprocshared=24\n"
        "%mem=48GB\n"
        "%chk=mol.chk\n"
        "#opt B3LYP/def2tzvp\n"
        "\n"
        "Untitled\n"
        "\n"
        "1 1\n"
        "C 0.0 0.0 0.0\n"
        "\n"
    )  # already ends with a blank line

    result = run_script("rung16", dest, "-t", "1-00:00:00", "-q", "test")

    assert result.returncode == 0, result.stderr
    assert "did not end with a blank line" not in result.stdout
