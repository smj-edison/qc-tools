"""
Extract key energies from Gaussian .log files and write a formatted Excel workbook.

Usage:
    python extract_energies.py <logfile> [<logfile> ...] -o <output.xlsx>

Produces an .xlsx matching the round-1.xlsx layout with columns:
    Structure | Stationary point? | Lowest frequency | SCF | ZPE | H | G | dE | dH | dG

Relative energies (dE, dH, dG) are written as Excel formulas so they update
automatically if the reference values are edited in the spreadsheet.
"""

import argparse
import glob
import re
import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Font

HARTREE_TO_KCAL = 627.5095


def _find_float(text: str, pattern: str) -> float | None:
    """Return the *last* match for pattern in text as a float."""
    matches = re.findall(pattern, text)
    if matches:
        try:
            return float(matches[-1])
        except ValueError:
            return None
    return None


def extract_energies(path: Path) -> dict:
    """Parse a Gaussian log file and return a dict of extracted data."""
    text = path.read_text()

    # Final SCF energy: the last occurrence of "SCF Done"
    scf_matches = re.findall(r"SCF Done:\s+E\(\S+\)\s+=\s+([-\d.]+)", text)
    scf_energy = float(scf_matches[-1]) if scf_matches else None

    zpe_total = _find_float(text, r"Sum of electronic and zero-point Energies=\s+([-\d.]+)")
    enthalpy = _find_float(text, r"Sum of electronic and thermal Enthalpies=\s+([-\d.]+)")
    gibbs = _find_float(text, r"Sum of electronic and thermal Free Energies=\s+([-\d.]+)")

    # Extract vibrational frequencies from "Frequencies --" lines
    freq_lines = re.findall(r"Frequencies\s+--\s+([-\d.\s]+)", text)
    frequencies = []
    for line in freq_lines:
        for token in line.split():
            try:
                frequencies.append(float(token))
            except ValueError:
                continue

    imaginary = [f for f in frequencies if f < 0]
    if not imaginary:
        stationary = "Yes"
    elif len(imaginary) == 1:
        stationary = "TS"
    else:
        stationary = "No"

    lowest_freq = min(frequencies) if frequencies else None

    return {
        "structure": path.stem,
        "scf_energy": scf_energy,
        "zpe_total": zpe_total,
        "enthalpy": enthalpy,
        "gibbs_free_energy": gibbs,
        "stationary": stationary,
        "lowest_frequency": lowest_freq,
    }


def write_excel(results: list[dict], output_path: Path) -> None:
    """Write results to an .xlsx matching the round-1.xlsx format."""
    wb = openpyxl.Workbook()
    ws = wb.active

    # Row 1: title row
    ws.cell(row=1, column=1, value="Filename")
    ws.cell(row=1, column=2, value=output_path.name)

    # Row 2: blank
    # Row 3: headers
    headers = [
        "Structure",
        "",
        "Stationary point?",
        "Lowest frequency",
        "SCF",
        "ZPE",
        "H",
        "G",
        "",
        "dZPE",
        "dE",
        "dH",
        "dG",
    ]
    for col, val in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=val)
        cell.font = Font(bold=True)

    # Reference row for formulas (first data row is row 4)
    ref_row = 4

    for i, r in enumerate(results, start=ref_row):
        ws.cell(row=i, column=1, value=r["structure"])
        ws.cell(row=i, column=2, value="")
        ws.cell(row=i, column=3, value=r["stationary"])
        ws.cell(row=i, column=4, value=r["lowest_frequency"])
        ws.cell(row=i, column=5, value=r["scf_energy"])
        ws.cell(row=i, column=6, value=r["zpe_total"])
        ws.cell(row=i, column=7, value=r["enthalpy"])
        ws.cell(row=i, column=8, value=r["gibbs_free_energy"])
        ws.cell(row=i, column=9, value="")
        # dZPE, dE, dH, dG as Excel formulas relative to the first row
        ws.cell(row=i, column=10, value=f"=(F{i}-F${ref_row})*{HARTREE_TO_KCAL}")
        ws.cell(row=i, column=11, value=f"=(E{i}-E${ref_row})*{HARTREE_TO_KCAL}")
        ws.cell(row=i, column=12, value=f"=(G{i}-G${ref_row})*{HARTREE_TO_KCAL}")
        ws.cell(row=i, column=13, value=f"=(H{i}-H${ref_row})*{HARTREE_TO_KCAL}")

    # Adjust column widths to fit content (cols 1-8)
    for col in range(1, 9):
        max_length = 0
        column_letter = openpyxl.utils.get_column_letter(col)
        for row in range(1, ws.max_row + 1):
            cell = ws.cell(row=row, column=col)
            if cell.value is not None:
                max_length = max(max_length, len(str(cell.value)))
        adjusted_width = max_length + 2
        ws.column_dimensions[column_letter].width = adjusted_width

    # Hardcode widths for formula columns (10-13)
    for col in (10, 11, 12, 13):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 12

    wb.save(output_path)
    print(f"Wrote {output_path}")


def _expand_paths(raw_paths: list[Path]) -> list[Path]:
    """Expand any glob patterns and return a sorted, deduplicated list of existing files."""
    expanded = set()
    for p in raw_paths:
        s = str(p)
        if '*' in s or '?' in s or '[' in s:
            for match in glob.glob(s, recursive=True):
                expanded.add(Path(match))
        else:
            expanded.add(p)
    # Sort for deterministic output and filter to existing files
    return sorted([p for p in expanded if p.exists()])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract energies from Gaussian .log files and write an Excel workbook."
    )
    parser.add_argument("logfile", nargs="+", type=Path, help="Gaussian .log file(s) or glob patterns")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output Excel file",
    )
    args = parser.parse_args()

    paths = _expand_paths(args.logfile)
    if not paths:
        print("No matching log files found.", file=sys.stderr)
        sys.exit(1)

    results = []
    for path in paths:
        results.append(extract_energies(path))

    write_excel(results, args.output)


if __name__ == "__main__":
    main()
