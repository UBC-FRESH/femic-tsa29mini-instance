"""Validate the TSA29 mini-instance model output."""
import geopandas as gpd
import pandas as pd

print("=" * 60)
print("TSA29 MINI-INSTANCE VALIDATION")
print("=" * 60)

# Check input fragments
print("\n1. INPUT FRAGMENTS (data/fragments.shp):")
input_df = gpd.read_file('data/fragments.shp')
print(f"   Count: {len(input_df)}")
print(f"   Area: {input_df['AREA_HA'].sum():.1f} ha")
print(f"   Columns: {input_df.columns.tolist()}")

# Check exported fragments
print("\n2. EXPORTED FRAGMENTS (output/patchworks_tsa29mini/fragments/):")
output_df = gpd.read_file('output/patchworks_tsa29mini/fragments/fragments.shp')
print(f"   Count: {len(output_df)}")
print(f"   Area: {output_df['AREA_HA'].sum():.1f} ha")
print(f"   Columns: {output_df.columns.tolist()}")

# Compare
print("\n3. COMPARISON:")
print(f"   Fragment count ratio: {len(output_df) / len(input_df):.2f}x")
print(f"   Area ratio: {output_df['AREA_HA'].sum() / input_df['AREA_HA'].sum():.2f}x")

# Check if they match
if len(output_df) == len(input_df) and abs(output_df['AREA_HA'].sum() - input_df['AREA_HA'].sum()) < 1:
    print("\n✓ PASS: Export matches input")
else:
    print("\n✗ FAIL: Export does NOT match input")
    print("   The export re-ran the full pipeline instead of using the subset!")

# Check forestmodel.xml exists
import os
fm_path = 'output/patchworks_tsa29mini/forestmodel.xml'
if os.path.exists(fm_path):
    size = os.path.getsize(fm_path)
    print(f"\n✓ forestmodel.xml exists ({size:,} bytes)")
else:
    print(f"\n✗ forestmodel.xml missing!")

print("\n" + "=" * 60)