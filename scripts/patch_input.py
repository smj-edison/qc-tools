import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path


def _read_paragraph(lines, i):
    """Return (paragraph_lines, new_index) reading until a blank line or EOF."""
    start = i
    n = len(lines)
    while i < n and lines[i].strip() != "":
        i += 1
    return lines[start:i], i


def _skip_blanks(lines, i):
    """Return first non-blank index at or after i."""
    n = len(lines)
    while i < n and lines[i].strip() == "":
        i += 1
    return i


def parse_gjf(path: Path):
    """
    Parse a Gaussian .gjf file into three parts:
      - header: link0 + route + title (everything before the molecule spec)
      - molecule: charge/spin line + atom coordinates (the third paragraph)
      - footer: everything after the molecule spec

    Per the Gaussian spec, the input is a sequence of blank-line-terminated
    sections.  The first paragraph absorbed into the header contains any
    link0 commands plus the route section; the second paragraph is the title;
    the third paragraph is the molecule specification.
    """
    lines = path.read_text().splitlines()
    i = 0

    # Paragraph 1: route (and any preceding link0 commands, since link0 is not
    # blank-line terminated and typically appears right before the route).
    i = _skip_blanks(lines, i)
    route_para, i = _read_paragraph(lines, i)

    # Paragraph 2: title
    i = _skip_blanks(lines, i)
    title_para, i = _read_paragraph(lines, i)

    # Paragraph 3: molecule specification
    i = _skip_blanks(lines, i)
    mol_start = i
    n = len(lines)
    while i < n and lines[i].strip() != "":
        i += 1
    mol_end = i

    header = route_para + [""] + title_para + [""]
    molecule = lines[mol_start:mol_end]
    footer = lines[i:]  # includes the terminating blank line and everything after
    return header, molecule, footer


def parse_orca(path: Path):
    """
    Parse an ORCA .inp file into three parts:
      - header: everything before the *xyz block
      - molecule: the *xyz block including the closing *
      - footer: everything after the *xyz block
    """
    lines = path.read_text().splitlines()

    mol_start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("*xyz") or stripped.startswith("*xyzfile"):
            mol_start = i
            break

    if mol_start is None:
        raise ValueError(f"No *xyz block found in {path}")

    mol_end = None
    for i in range(mol_start + 1, len(lines)):
        if lines[i].strip() == "*":
            mol_end = i
            break

    if mol_end is None:
        raise ValueError(f"No closing * found for *xyz block in {path}")

    header = lines[:mol_start]
    molecule = lines[mol_start : mol_end + 1]
    footer = lines[mol_end + 1 :]
    return header, molecule, footer


def parse_xyz(path: Path):
    """Read an XYZ file and return formatted coordinate lines, preserving original element labels.

    Handles both standard XYZ (atom count + comment header) and headerless XYZ.
    """
    text = path.read_text()
    lines_raw = text.splitlines()

    i = 0
    # Skip blank lines at the top
    while i < len(lines_raw) and not lines_raw[i].strip():
        i += 1

    # Standard XYZ: first non-blank line is the atom count.
    if i < len(lines_raw) and lines_raw[i].strip().lstrip("-").isdigit():
        i += 1  # skip count
        # Skip comment/title line
        while i < len(lines_raw) and not lines_raw[i].strip():
            i += 1
        i += 1

    coord_lines = []
    for line in lines_raw[i:]:
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if len(parts) >= 4:
            element = parts[0]
            x, y, z = parts[1], parts[2], parts[3]
            coord_lines.append(f"{element:2s}  {float(x):11.8f}  {float(y):11.8f}  {float(z):11.8f}")
    return coord_lines


def _extract_charge_spin(molecule: list[str], format_type: str) -> str:
    """Extract charge and spin from a molecule block."""
    if not molecule:
        return "0 1"
    if format_type == "orca":
        parts = molecule[0].strip().split()
        if len(parts) >= 3:
            return f"{parts[1]} {parts[2]}"
    return molecule[0].strip()


def _extract_coords(molecule: list[str], format_type: str) -> list[str]:
    """Extract coordinate lines from a molecule block."""
    if format_type == "orca":
        coords = []
        for line in molecule[1:]:
            stripped = line.strip()
            if stripped == "*":
                break
            if stripped:
                coords.append(stripped)
        return coords
    else:
        return molecule[1:] if len(molecule) > 1 else []


def _format_molecule(coords: list[str], charge_spin: str, format_type: str) -> list[str]:
    """Format coordinates into a molecule block for the target format."""
    if format_type == "orca":
        parts = charge_spin.split()
        if len(parts) >= 2:
            cs = f"{parts[0]} {parts[1]}"
        else:
            cs = "0 1"
        lines = [f"*xyz {cs}"]
        lines.extend(coords)
        lines.append("*")
        return lines
    else:
        return [charge_spin] + coords


def _pick_source(by_stem: dict):
    """From stem->[paths], return list of (stem, path) preferring .gjf over .inp over .xyz."""
    sources = []
    for stem in sorted(by_stem):
        files = by_stem[stem]
        gjf = next((f for f in files if f.suffix.lower() == ".gjf"), None)
        inp = next((f for f in files if f.suffix.lower() == ".inp"), None)
        sources.append((stem, gjf if gjf else (inp if inp else files[0])))
    return sources


def patch_template(
    template_path: Path, source_path: Path, stem: str, prefix: str | None, out_dir: Path
):
    """
    Generate a patched file from template + source file.
    Supports Gaussian (.gjf) and ORCA (.inp) templates.
    Source may be .gjf, .inp, or .xyz.
    """
    template_suffix = template_path.suffix.lower()

    if template_suffix == ".gjf":
        header, template_molecule, footer = parse_gjf(template_path)
        target_format = "gjf"
    elif template_suffix == ".inp":
        header, template_molecule, footer = parse_orca(template_path)
        target_format = "orca"
    else:
        raise ValueError(f"Unsupported template format: {template_suffix}")

    source_suffix = source_path.suffix.lower()
    if source_suffix == ".gjf":
        _, source_molecule, _ = parse_gjf(source_path)
        source_format = "gjf"
    elif source_suffix == ".inp":
        _, source_molecule, _ = parse_orca(source_path)
        source_format = "orca"
    elif source_suffix == ".xyz":
        coords = parse_xyz(source_path)
        charge_spin = _extract_charge_spin(template_molecule, target_format)
        molecule = _format_molecule(coords, charge_spin, target_format)
    else:
        raise ValueError(f"Unsupported source format: {source_suffix}")

    if source_suffix != ".xyz":
        charge_spin = _extract_charge_spin(source_molecule, source_format)
        coords = _extract_coords(source_molecule, source_format)
        molecule = _format_molecule(coords, charge_spin, target_format)

    if prefix is None:
        out_name = f"{stem}{template_suffix}"
    elif "%" in prefix:
        try:
            out_name = prefix % int(stem)
        except ValueError:
            print(
                f"Warning: prefix '{prefix}' requires a numeric stem, but got '{stem}'. Skipping.",
                file=sys.stderr,
            )
            return
    else:
        out_name = f"{prefix}{stem}"
        if not out_name.endswith(template_suffix):
            out_name += template_suffix

    out_path = out_dir / out_name
    out_dir.mkdir(parents=True, exist_ok=True)

    def patch_chk_line(line: str) -> str:
        if line.strip().startswith("%chk="):
            chk_name = out_name.removesuffix(template_suffix)
            old_path = line.strip().split("=", 1)[1]
            old_dir = os.path.dirname(old_path)
            if old_dir:
                return f"%chk={old_dir}/{chk_name}.chk"
            return f"%chk={chk_name}.chk"
        return line

    if target_format == "gjf":
        patched_header = [patch_chk_line(l) for l in header]
        patched_footer = [patch_chk_line(l) for l in footer]
    else:
        patched_header = header
        patched_footer = footer

    with out_path.open("w", newline="\n") as f:
        for line in patched_header:
            f.write(line + "\n")
        for line in molecule:
            f.write(line + "\n")
        for line in patched_footer:
            f.write(line + "\n")

    print(f"Wrote {out_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Patch a Gaussian (.gjf) or ORCA (.inp) template with molecule specs from source files."
    )
    parser.add_argument("template", type=Path, help="Template .gjf or .inp file")
    parser.add_argument(
        "-p",
        "--prefix",
        default=None,
        help=(
            "Output filename template. Use %%d for the number, e.g. 'TS%%d.gjf'. "
            "If omitted, the source stem with the template extension is used."
        ),
    )
    parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=Path("."),
        help="Directory containing source files (default: current dir)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("."),
        help="Directory to write patched files (default: current dir)",
    )
    parser.add_argument(
        "-i",
        "--input",
        action="append",
        nargs="+",
        help="Glob pattern(s) for source files. May be repeated. If omitted, numeric .gjf/.xyz/.inp files are discovered automatically.",
    )
    args = parser.parse_args()

    if not args.template.exists():
        print(f"Error: template file {args.template} not found.", file=sys.stderr)
        sys.exit(1)

    if args.input:
        by_stem = defaultdict(list)
        # Flatten list of lists from nargs='+' with action='append'
        patterns = [p for group in args.input for p in group]
        for pattern in patterns:
            for f in sorted(args.directory.glob(pattern)):
                if f.name == args.template.name:
                    continue
                if f.suffix.lower() in (".gjf", ".xyz", ".inp"):
                    by_stem[f.stem].append(f)
        sources = _pick_source(by_stem)
    else:
        by_stem = defaultdict(list)
        for f in sorted(args.directory.glob("*.gjf")):
            if f.name == args.template.name:
                continue
            if f.stem.isdigit():
                by_stem[f.stem].append(f)
        for f in sorted(args.directory.glob("*.inp")):
            if f.name == args.template.name:
                continue
            if f.stem.isdigit():
                by_stem[f.stem].append(f)
        for f in sorted(args.directory.glob("*.xyz")):
            if f.stem.isdigit():
                by_stem[f.stem].append(f)
        sources = _pick_source(by_stem)
        sources.sort(key=lambda x: int(x[0]))

    if not sources:
        print("No source files found.", file=sys.stderr)
        sys.exit(1)

    for stem, source_path in sources:
        patch_template(args.template, source_path, stem, args.prefix, args.output)


if __name__ == "__main__":
    main()
