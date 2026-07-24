"""Validate the TSA29 mini-instance pre-compiled data."""
import geopandas as gpd
import pandas as pd
import os

print("=" * 70)
print("TSA29 MINI-INSTANCE PRE-COMPILED DATA VALIDATION")
print("=" * 70)

errors = []
warnings = []

# 1. Check fragments.shp
print("\n1. FRAGMENTS (data/fragments.shp):")
try:
    frag = gpd.read_file('data/fragments.shp')
    print(f"   Count: {len(frag)}")
    print(f"   Area: {frag['AREA_HA'].sum():.1f} ha")
    print(f"   CRS: {frag.crs}")
    print(f"   Columns: {frag.columns.tolist()}")
    
    # Check required columns
    required_cols = ['FRAGMENT_I', 'BLOCK', 'AREA_HA', 'F_AGE', 'AU', 'IFM', 'ORIGIN', 'SILV_STATE', 'RETENTION', 'TSA', 'VRI_FID']
    missing_cols = [c for c in required_cols if c not in frag.columns]
    if missing_cols:
        errors.append(f"fragments.shp missing columns: {missing_cols}")
    else:
        print(f"   ✓ All required columns present")
    
    # Check AU values
    au_values = frag['AU'].unique()
    print(f"   Unique AUs: {len(au_values)}")
    print(f"   AU values: {sorted(au_values)}")
    
    # Check TSA values
    tsa_values = frag['TSA'].unique()
    print(f"   TSA values: {tsa_values}")
    
except Exception as e:
    errors.append(f"Failed to read fragments.shp: {e}")

# 2. Check au_table
print("\n2. AU TABLE (data/model_input_bundle/au_table.csv):")
try:
    au_table = pd.read_csv('data/model_input_bundle/au_table.csv')
    print(f"   Rows: {len(au_table)}")
    print(f"   Columns: {au_table.columns.tolist()}")
    
    # Check AU values match
    au_table_aus = set(au_table['au_id'].astype(str))
    frag_aus = set(frag['AU'].astype(str))
    missing_in_au_table = frag_aus - au_table_aus
    extra_in_au_table = au_table_aus - frag_aus
    
    if missing_in_au_table:
        errors.append(f"AUs in fragments but not in au_table: {missing_in_au_table}")
    else:
        print(f"   ✓ All fragment AUs present in au_table")
    
    if extra_in_au_table:
        warnings.append(f"AUs in au_table but not in fragments: {extra_in_au_table}")
        print(f"   ⚠ {len(extra_in_au_table)} extra AUs in au_table")
    
    # Check curve IDs
    print(f"   Untreated curves: {au_table['untreated_curve_id'].nunique()}")
    print(f"   Treated curves: {au_table['treated_curve_id'].nunique()}")
    
except Exception as e:
    errors.append(f"Failed to read au_table.csv: {e}")

# 3. Check curve tables
print("\n3. CURVE TABLES:")
try:
    curve_table = pd.read_csv('data/model_input_bundle/curve_table.csv')
    curve_points = pd.read_csv('data/model_input_bundle/curve_points_table.csv')
    print(f"   curve_table.csv: {len(curve_table)} rows")
    print(f"   curve_points_table.csv: {len(curve_points)} rows")
    
    # Check if curves referenced by au_table exist
    au_table_curves = set(int(x) for x in au_table['untreated_curve_id'].dropna().unique()) | set(int(x) for x in au_table['treated_curve_id'].dropna().unique())
    curve_table_curves = set(int(x) for x in curve_table['curve_id'].unique())
    missing_curves = au_table_curves - curve_table_curves
    
    if missing_curves:
        errors.append(f"Curves in au_table but not in curve_table: {missing_curves}")
    else:
        print(f"   ✓ All curves referenced by au_table exist in curve_table")
    
except Exception as e:
    errors.append(f"Failed to read curve tables: {e}")

# 4. Check vdyp data
print("\n4. VDYP DATA:")
try:
    vdyp_ply = pd.read_feather('data/vdyp_ply-tsa29mini.feather')
    vdyp_lyr = pd.read_feather('data/vdyp_lyr-tsa29mini.feather')
    print(f"   vdyp_ply: {len(vdyp_ply)} rows")
    print(f"   vdyp_lyr: {len(vdyp_lyr)} rows")
    
    # Check if VRI_FIDs from fragments are in vdyp data
    frag_vri_fids = set(frag['VRI_FID'].astype(str))
    vdyp_ply_fids = set(vdyp_ply['FEATURE_ID'].astype(str))
    missing_fids = frag_vri_fids - vdyp_ply_fids
    
    if missing_fids:
        warnings.append(f"{len(missing_fids)} VRI_FIDs in fragments but not in vdyp_ply")
        print(f"   ⚠ {len(missing_fids)} VRI_FIDs missing from vdyp_ply")
    else:
        print(f"   ✓ All VRI_FIDs from fragments present in vdyp_ply")
    
except Exception as e:
    errors.append(f"Failed to read vdyp data: {e}")

# 5. Check tipsy config
print("\n5. TIPSY CONFIG:")
try:
    import yaml
    with open('config/tipsy/tsa29mini.yaml', 'r') as f:
        tipsy_config = yaml.safe_load(f)
    
    if 'rules' in tipsy_config and tipsy_config['rules']:
        print(f"   ✓ Rules present: {len(tipsy_config['rules'])} rules")
    else:
        errors.append("TIPSY config missing 'rules'")
    
    if 'species_code_overrides' in tipsy_config:
        print(f"   Species overrides: {tipsy_config['species_code_overrides']}")
    
except Exception as e:
    errors.append(f"Failed to read tipsy config: {e}")

# Summary
print("\n" + "=" * 70)
print("VALIDATION SUMMARY")
print("=" * 70)

if errors:
    print(f"\n✗ FAILED with {len(errors)} error(s):")
    for i, err in enumerate(errors, 1):
        print(f"   {i}. {err}")
else:
    print("\n✓ ALL CHECKS PASSED")

if warnings:
    print(f"\n⚠ {len(warnings)} warning(s):")
    for i, warn in enumerate(warnings, 1):
        print(f"   {i}. {warn}")

print("\n" + "=" * 70)