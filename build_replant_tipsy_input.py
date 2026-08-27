#!/usr/bin/env python3
"""Build the BatchTIPSY (BTC) input for tsa29mini species-switching replant
options (fresh-fuchs phase P6, issue #48).

Context: the tsa29mini bundle ships treated/untreated aggregate curves only
(inherited from the parent tsa29 managed AUs via
``au_table.source_managed_local_au_id``). The species-switching replant
feature needs yield curves for replanting each source AU with a *different*
species than its source stratum. This script emits pure-plantation BTC input
rows for every source AU x target species combination (63 rows), plus a
manifest mapping each new feature_id back to its provenance.

Option matrix (pure plantations only; species mixes deferred):

- target species: PL, SW (hybrid spruce; canonical SX), FD
- every source AU (7 strata x L/M/H SI levels = 21 AUs) gets all three
- SI for the target species: the source AU's reference SI, flat-transferred
  to the target species column (documented simplification; the parent tsa29
  SiteProd pull carries one SI per AU, not species-specific SIs)
- planting parameters (TSR-informed, from the tsa29 TIPSY rules/artifacts):
    PL: density 971 sph (SBPS) / 895 sph (IDF), GW 3.0, delay 4 (SBPS) / 2 (IDF)
    SW: density 1100 sph, GW blank (matches tsa29 pure-Sw rows), delay 1
    FD: density 934 sph, GW 9.0, delay 4 (SBPS) / 2 (IDF)
- OAF1/OAF2: copied from the mapped tsa29 managed-AU row (OAF2 = 0.95)
- planted_percent = 100 (pure plantation, no natural ingress payload)

Usage:
    python build_replant_tipsy_input.py --tsa29-input <path to 03_input-tsa29.csv>

Outputs (relative to this instance root):
    data/03_input-tsa29mini-replant.csv   BTC MSYT-schema input rows
    data/tipsy_replant_manifest-tsa29mini.csv   feature_id -> provenance map
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

INSTANCE_ROOT = Path(__file__).resolve().parent
AU_TABLE = INSTANCE_ROOT / "data" / "model_input_bundle" / "au_table.csv"
OUT_INPUT = INSTANCE_ROOT / "data" / "03_input-tsa29mini-replant.csv"
OUT_MANIFEST = INSTANCE_ROOT / "data" / "tipsy_replant_manifest-tsa29mini.csv"

# TIPSY species code -> (planted code, SI column, option index).
TARGET_SPECIES = {
    "PL": {"planted": "Pl", "si_col": "pl_si", "idx": 1},
    "SW": {"planted": "Sw", "si_col": "sw_si", "idx": 2},
    "FD": {"planted": "Fd", "si_col": "fd_si", "idx": 3},
}

# TSR-informed planting defaults per target species (see module docstring).
SPECIES_PARAMS = {
    "PL": {"gw": "3.0"},
    "SW": {"gw": ""},
    "FD": {"gw": "9.0"},
}
DENSITY = {  # stems/ha by target species and BEC zone
    "PL": {"SBPS": 971, "IDF": 895},
    "SW": {"SBPS": 1100, "IDF": 1100},
    "FD": {"SBPS": 934, "IDF": 934},
}
PLANTING_DELAY = {  # years by target species and BEC zone
    "PL": {"SBPS": 4, "IDF": 2},
    "SW": {"SBPS": 1, "IDF": 1},
    "FD": {"SBPS": 4, "IDF": 2},
}

FEATURE_ID_BASE = 600000  # replant-option curve namespace: 6xxxxx

SI_COLUMNS = [
    "at_si", "ba_si", "bg_si", "bl_si", "cw_si", "dr_si", "ep_si", "fd_si",
    "hm_si", "hw_si", "lt_si", "lw_si", "pa_si", "pl_si", "pw_si", "py_si",
    "sb_si", "se_si", "ss_si", "sw_si", "sx_si", "yc_si",
]

BTC_COLUMNS = [
    "feature_id", "bec_zone", "bec_subzone",
    "planted_species1", "planted_species2", "planted_species3",
    "planted_species4", "planted_species5",
    "planted_density1", "planted_density2", "planted_density3",
    "planted_density4", "planted_density5",
    "genetic_worth1", "genetic_worth2", "genetic_worth3",
    "genetic_worth4", "genetic_worth5",
    "planting_delay", "planted_percent",
    "natural_species1", "natural_species2", "natural_species3",
    "natural_species4", "natural_species5",
    "natural_density1", "natural_density2", "natural_density3",
    "natural_density4", "natural_density5",
    "oaf1", "oaf2", "opening_id", "vri_ref_age", "vri_ref_sph",
    *SI_COLUMNS,
]

MANIFEST_COLUMNS = [
    "feature_id", "au_id", "stratum_code", "si_level", "bec_zone",
    "target_species", "si_used", "si_source_column", "density_sph",
    "genetic_worth", "planting_delay", "oaf1", "oaf2",
    "source_tsa29_feature_id", "notes",
]


def _reference_si(tsa29_row: dict[str, str]) -> tuple[float, str]:
    """Return the source AU's reference SI and the column it came from."""
    for col in ("pl_si", "sw_si", "fd_si"):
        value = float(tsa29_row.get(col) or 0.0)
        if value > 0:
            return value, col
    raise ValueError(
        f"no reference SI in tsa29 row {tsa29_row.get('feature_id')}"
    )


def build_rows(tsa29_input: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    with open(AU_TABLE, newline="") as f:
        au_rows = list(csv.DictReader(f))
    with open(tsa29_input, newline="") as f:
        tsa29_rows = {int(r["feature_id"]): r for r in csv.DictReader(f)}

    input_rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []
    for au in au_rows:
        au_id = int(au["au_id"])
        local_au = int(au["source_local_au_id"])
        managed_ref = int(au["source_managed_local_au_id"])
        stratum = au["stratum_code"]
        si_level = au["si_level"]
        bec = stratum.split("_")[0]
        ref_row = tsa29_rows.get(managed_ref)
        if ref_row is None:
            raise KeyError(f"au_id {au_id}: tsa29 row {managed_ref} not found")
        ref_si, ref_si_col = _reference_si(ref_row)
        oaf1 = ref_row["oaf1"]
        for sp, meta in TARGET_SPECIES.items():
            feature_id = FEATURE_ID_BASE + local_au * 10 + meta["idx"]
            row = {c: "" for c in BTC_COLUMNS}
            row.update(
                {
                    "feature_id": str(feature_id),
                    "bec_zone": bec,
                    "bec_subzone": "",
                    "planted_species1": meta["planted"],
                    "planted_density1": str(DENSITY[sp][bec]),
                    "genetic_worth1": SPECIES_PARAMS[sp]["gw"],
                    "planting_delay": str(PLANTING_DELAY[sp][bec]),
                    "planted_percent": "100",
                    "oaf1": oaf1,
                    "oaf2": "0.95",
                    "opening_id": str(feature_id),
                    "vri_ref_age": "0",
                    "vri_ref_sph": "0",
                }
            )
            for col in SI_COLUMNS:
                row[col] = "0"
            row[meta["si_col"]] = str(ref_si)
            input_rows.append(row)
            manifest_rows.append(
                {
                    "feature_id": str(feature_id),
                    "au_id": str(au_id),
                    "stratum_code": stratum,
                    "si_level": si_level,
                    "bec_zone": bec,
                    "target_species": sp,
                    "si_used": str(ref_si),
                    "si_source_column": ref_si_col,
                    "density_sph": str(DENSITY[sp][bec]),
                    "genetic_worth": SPECIES_PARAMS[sp]["gw"],
                    "planting_delay": str(PLANTING_DELAY[sp][bec]),
                    "oaf1": oaf1,
                    "oaf2": "0.95",
                    "source_tsa29_feature_id": str(managed_ref),
                    "notes": "flat SI transfer from source AU reference SI",
                }
            )
    return input_rows, manifest_rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tsa29-input",
        type=Path,
        required=True,
        help="Path to the parent tsa29 instance's 03_input-tsa29.csv.",
    )
    args = parser.parse_args()
    input_rows, manifest_rows = build_rows(args.tsa29_input)
    with open(OUT_INPUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=BTC_COLUMNS)
        writer.writeheader()
        writer.writerows(input_rows)
    with open(OUT_MANIFEST, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"wrote {len(input_rows)} BTC input rows -> {OUT_INPUT}")
    print(f"wrote {len(manifest_rows)} manifest rows -> {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
