import argparse
import os
import sys
import importlib
from pathlib import Path
from typing import Sequence, Tuple, List

import pandas as pd

from tools.utils import Utils

# Add parent directory to path to import tools
sys.path.insert(0, str(Path(__file__).parent))

def discover_tools():
    """Discover and list all available tools from the tools folder."""
    tools_dir = Path(__file__).parent / "tools"
    tools = {}
    
    for tool_file in tools_dir.glob("*.py"):
        # Skip __init__.py and utils.py
        if tool_file.name.startswith("_") or tool_file.name == "utils.py":
            continue
        
        # Skip shell scripts
        if tool_file.suffix != ".py":
            continue
        
        tool_name = tool_file.stem
        tools[tool_name] = tool_file
    
    return tools


def _parse_tags(path_str: str) -> Tuple[List[str], List[str], List[str]]:
    """Return (prefix_parts, filters, enrichments) from a filename following our nomenclature."""
    fname = Path(path_str).name
    parts = [p for p in Path(fname).stem.split("_") if p]
    prefix: List[str] = []
    filters: List[str] = []
    enrichments: List[str] = []
    i = 0
    while i < len(parts):
        token = parts[i].lower()
        if token == "filtered":
            i += 1
            while i < len(parts) and parts[i].lower() not in {"filtered", "enriched"}:
                filters.append(parts[i].lower())
                i += 1
            continue
        if token == "enriched":
            i += 1
            while i < len(parts) and parts[i].lower() not in {"filtered", "enriched"}:
                enrichments.append(parts[i].lower())
                i += 1
            continue
        prefix.append(parts[i])
        i += 1
    return prefix, filters, enrichments


def combine_csvs(input_files: Sequence[str], output_file: str | None = None, id_field: str = "observation_uuid", intersect: bool = True):
    """
    Combine plusieurs CSV en fusionnant les lignes par identifiant unique (id_field).
    - input_files : chemins vers les CSV à fusionner
    - output_file : optionnel, sinon dérivé du premier fichier avec union des filtres/enrichissements
    - id_field : nom de la colonne identifiant unique (par défaut 'observation_uuid')
    """
    if not input_files:
        raise ValueError("Aucun fichier en entrée pour combine_csvs.")

    # Charger et fusionner par identifiant
    combined_df = None
    for path in input_files:
        df = pd.read_csv(path)
        if id_field not in df.columns:
            raise ValueError(f"Le fichier {path} ne contient pas la colonne identifiante '{id_field}'.")
        df = df.set_index(id_field)
        if combined_df is None:
            combined_df = df
            continue
        if intersect:
            common_idx = combined_df.index.intersection(df.index)
            combined_df = combined_df.loc[common_idx]
            df = df.loc[common_idx]
        else:
            combined_df = combined_df.reindex(combined_df.index.union(df.index))
        for col in df.columns:
            if col in combined_df.columns:
                combined_df[col] = combined_df[col].combine_first(df[col])
            else:
                combined_df[col] = df[col]

    combined_df = combined_df.reset_index()

    # Union des filtres/enrichissements pour le nom de sortie
    prefixes, filters_all, enrich_all = [], [], []
    for f in input_files:
        p, fts, ens = _parse_tags(f)
        if p:
            prefixes.append("_".join(p))
        filters_all.extend(fts)
        enrich_all.extend(ens)

    # Base du nom = prefix du premier fichier sinon "combined"
    base_prefix = prefixes[0] if prefixes else "combined"
    base_path = Path(input_files[0]).parent / base_prefix
    out_path = output_file or str(base_path) + ".csv"

    # Appliquer les tags via Utils.name_file (qui déduplique et préserve l'ordre)
    if filters_all:
        out_path = Utils.name_file(out_path, "filtered", filters_all)
    if enrich_all:
        out_path = Utils.name_file(out_path, "enriched", enrich_all)

    out_path = os.path.join(Utils.DATA_PROCESSED_DIR, os.path.basename(out_path))
    combined_df.to_csv(out_path, index=False)
    print(f"Combined {len(input_files)} files into {out_path}")

def main():
    tools = discover_tools()
    special_tools = {"combine_csvs": combine_csvs}
    tool_choices = list(tools.keys()) + list(special_tools.keys())
    
    # Parse only the tool name and pass remaining args to the tool
    parser = argparse.ArgumentParser(description="Ecosystems main application")
    parser.add_argument("tool", choices=tool_choices, help="Tool to run")
    
    # Parse just the tool name, everything else goes to the tool
    args, tool_args = parser.parse_known_args()
    
    if args.tool in special_tools:
        # handle combine_csvs
        if args.tool == "combine_csvs":
            cparser = argparse.ArgumentParser(description="Combiner plusieurs CSV en fusionnant les lignes par identifiant.")
            cparser.add_argument("inputs", nargs="+", help="Liste des CSV à fusionner.")
            cparser.add_argument("--out", dest="out", default=None, help="Chemin de sortie (optionnel).")
            cparser.add_argument("--id", dest="id_field", default="observation_uuid", help="Nom de la colonne identifiante (défaut: id).")
            cparser.add_argument("--intersect", dest="intersect", action="store_true", help="Utiliser l'intersection des index au lieu de l'union.")
            cargs = cparser.parse_args(tool_args)
            combine_csvs(cargs.inputs, cargs.out, id_field=cargs.id_field, intersect=cargs.intersect)
        else:
            special_tools[args.tool](*tool_args)
        return

    # Dynamically import and run the selected tool
    tool_module = importlib.import_module(f"tools.{args.tool}")
    
    # Try to call main() if it exists, otherwise run the module
    if hasattr(tool_module, "main"):
        # Pass remaining arguments directly to the tool's main function
        import sys
        original_argv = sys.argv
        try:
            # Replace sys.argv with the tool's arguments for its argparse
            sys.argv = [sys.argv[0]] + tool_args
            tool_module.main()
        finally:
            # Restore original argv
            sys.argv = original_argv
    else:
        print(f"Warning: Tool '{args.tool}' does not have a main() function.")

if __name__ == "__main__":
    main()
