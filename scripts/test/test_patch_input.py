def test_patches_xyz_source_using_template_charge_spin(run_script, templates_dir, tmp_path):
    template = templates_dir / "B3LYP IN template.gjf"
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "1.xyz").write_text("2\ncomment\nO 0.0 0.0 0.0\nH 0.0 0.0 1.0\n")
    out_dir = tmp_path / "out"

    result = run_script(
        "patch_input", template, "-d", src_dir, "-o", out_dir, "-i", "*.xyz"
    )

    assert result.returncode == 0, result.stderr
    out_file = out_dir / "1.gjf"
    assert out_file.exists()
    content = out_file.read_text()
    assert "%chk=1.chk" in content
    assert "1 1" in content  # charge/spin carried over from the template
    assert "O " in content
    assert "H " in content


def test_patches_gjf_source_with_prefix_and_own_charge_spin(run_script, templates_dir, tmp_path):
    template = templates_dir / "B3LYP IN template.gjf"
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "3.gjf").write_text(
        "%nprocshared=8\n%mem=16GB\n%chk=whatever\n#route\n\nTitle\n\n0 1\nC 0.0 0.0 0.0\n\n"
    )
    out_dir = tmp_path / "out"

    result = run_script("patch_input", template, "-d", src_dir, "-o", out_dir, "-p", "TS%d.gjf")

    assert result.returncode == 0, result.stderr
    out_file = out_dir / "TS3.gjf"
    assert out_file.exists()
    content = out_file.read_text()
    assert "%chk=TS3.chk" in content
    assert "0 1" in content  # charge/spin taken from the source file, not the template
    assert "C " in content


def test_missing_template_errors(run_script, tmp_path):
    result = run_script("patch_input", tmp_path / "nope.gjf")

    assert result.returncode != 0
    assert "not found" in result.stderr
