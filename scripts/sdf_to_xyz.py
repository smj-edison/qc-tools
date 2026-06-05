import argparse
import sys

from rdkit import Chem


def convert_sdf_to_xyz(input_path: str, output_path: str) -> int:
    """Convert an SDF file to XYZ. Returns number of molecules written."""
    supplier = Chem.SDMolSupplier(input_path, removeHs=False)
    mols = [mol for mol in supplier if mol is not None]

    if not mols:
        raise ValueError(f"No valid molecules found in {input_path}")

    if len(mols) == 1:
        Chem.MolToXYZFile(mols[0], output_path)
        return 1

    # Multi-molecule: write numbered files
    base, ext = output_path.rsplit(".", 1) if "." in output_path else (output_path, "xyz")
    for i, mol in enumerate(mols):
        fname = f"{base}_{i+1}.{ext}"
        Chem.MolToXYZFile(mol, fname)

    return len(mols)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert SDF to XYZ format.")
    parser.add_argument("input", help="Input SDF file")
    parser.add_argument("output", help="Output XYZ file")
    args = parser.parse_args()

    try:
        n = convert_sdf_to_xyz(args.input, args.output)
        if n > 1:
            print(f"Wrote {n} molecules to numbered files.")
        else:
            print(f"Wrote {args.output}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
