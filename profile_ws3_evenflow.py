"""
Standalone profiler for the ws3 Woodstock-bootstrap even-flow optimization.
Runs the full notebook pipeline with simple wall-clock timing and cProfile output.
"""
import os
import sys
import time
import cProfile
import pstats
import io
from pathlib import Path

import pandas as pd
import numpy as np
import geopandas as gpd

import ws3.forest
import ws3.opt
import ws3.core
from femic.fmg.adapters import build_bundle_model_context_from_tables
from femic.fmg.woodstock import (
    build_woodstock_yields_table,
    build_woodstock_actions_table,
    build_woodstock_transitions_table,
)

INSTANCE_ROOT = Path(__file__).parent.resolve()
BUNDLE_DIR = INSTANCE_ROOT / 'data' / 'model_input_bundle'
FRAGMENTS_PATH = INSTANCE_ROOT / 'output' / 'patchworks_tsa29mini' / 'fragments' / 'fragments.shp'
WOODSTOCK_DIR = INSTANCE_ROOT / 'output' / 'patchworks_tsa29mini' / 'ws3_woodstock_bootstrap_model'
WOODSTOCK_DIR.mkdir(parents=True, exist_ok=True)
MODEL_NAME = 'tsa29mini'

PERIOD_LENGTH = 10
HORIZON = int(os.environ.get('HORIZON', '30'))
WORKERS = int(os.environ.get('WORKERS', '1'))
MAX_AGE = 300  # match Patchworks max age
MIN_HARVEST_AGE = 60
MAX_HARVEST_AGE = 300  # cap harvest operability at Patchworks max age


def tic(label):
    print(f'[{time.strftime("%H:%M:%S")}] START {label}', flush=True)
    return time.perf_counter()


def toc(start, label):
    elapsed = time.perf_counter() - start
    print(f'[{time.strftime("%H:%M:%S")}] DONE  {label}: {elapsed:.2f}s', flush=True)
    return elapsed


def main():
    timings = {}

    t0 = tic('Build bundle context')
    au_table = pd.read_csv(BUNDLE_DIR / 'au_table.csv')
    curve_table = pd.read_csv(BUNDLE_DIR / 'curve_table.csv')
    curve_points_table = pd.read_csv(BUNDLE_DIR / 'curve_points_table.csv')
    context = build_bundle_model_context_from_tables(
        au_table=au_table,
        curve_table=curve_table,
        curve_points_table=curve_points_table,
        tsa_list=['29'],
        bundle_dir=BUNDLE_DIR,
    )
    timings['bundle_context'] = toc(t0, 'Build bundle context')

    t0 = tic('Build Woodstock tables')
    yields_df = build_woodstock_yields_table(context=context)
    actions_df = build_woodstock_actions_table(
        context=context,
        cc_min_age=MIN_HARVEST_AGE,
        cc_max_age=MAX_AGE,
    )
    transitions_df = build_woodstock_transitions_table(context=context)
    timings['woodstock_tables'] = toc(t0, 'Build Woodstock tables')

    t0 = tic('Build areas with retention split')
    fragments = gpd.read_file(FRAGMENTS_PATH)
    fragments['area_ha'] = pd.to_numeric(fragments['AREA_HA'], errors='coerce').fillna(0.0)
    fragments['retention'] = pd.to_numeric(fragments['RETENTION'], errors='coerce').fillna(0.0).clip(0.0, 1.0)

    area_rows = []
    for _, row in fragments.iterrows():
        base = {
            'tsa': str(row['TSA']),
            'au_id': int(row['AU']),
            'origin': str(row['ORIGIN']),
            'silv_state': str(row['SILV_STATE']),
            'age': int(row['F_AGE']),
        }
        area = row['area_ha']
        retention = row['retention']
        ifm = str(row['IFM'])
        if ifm == 'managed' and retention > 0.0:
            managed_area = area * (1.0 - retention)
            unmanaged_area = area * retention
            if managed_area > 0.0:
                r = base.copy()
                r.update({'ifm': 'managed', 'area_ha': managed_area})
                area_rows.append(r)
            if unmanaged_area > 0.0:
                r = base.copy()
                r.update({'ifm': 'unmanaged', 'area_ha': unmanaged_area})
                area_rows.append(r)
        else:
            r = base.copy()
            r.update({'ifm': ifm, 'area_ha': area})
            area_rows.append(r)
    areas_df = pd.DataFrame(area_rows)
    timings['areas_split'] = toc(t0, 'Build areas with retention split')

    print(f'Fragments: {len(fragments):,}, total area: {fragments["AREA_HA"].sum():.1f} ha')
    print(f'Area records after retention split: {len(areas_df):,}')
    print(f'Managed area after split: {areas_df[areas_df["ifm"] == "managed"]["area_ha"].sum():.1f} ha')
    print(f'Unmanaged area after split: {areas_df[areas_df["ifm"] == "unmanaged"]["area_ha"].sum():.1f} ha')

    t0 = tic('Write Woodstock files')
    au_ids = sorted(fragments['AU'].unique().astype(int).tolist())
    with open(WOODSTOCK_DIR / f'{MODEL_NAME}.lan', 'w') as f:
        f.write('*THEME TSA\n')
        f.write('29\n\n')
        f.write('*THEME IFM\n')
        f.write('managed\n')
        f.write('unmanaged\n\n')
        f.write('*THEME AU\n')
        for au in au_ids:
            f.write(f'{au}\n')
        f.write('\n')
        f.write('*THEME ORIGIN\n')
        f.write('natural\n')
        f.write('planted\n\n')
        f.write('*THEME SILV_STATE\n')
        f.write('baseline\n')
        f.write('cc_pl\n\n')

    with open(WOODSTOCK_DIR / f'{MODEL_NAME}.are', 'w') as f:
        for _, row in areas_df.iterrows():
            if row['area_ha'] <= 0:
                continue
            f.write(
                f"*A {row['tsa']} {row['ifm']} {row['au_id']} {row['origin']} {row['silv_state']} "
                f"{int(row['age'])} {row['area_ha']:.6f}\n"
            )

    with open(WOODSTOCK_DIR / f'{MODEL_NAME}.yld', 'w') as f:
        for (tsa, au_id, ifm, curve_id), group in yields_df.groupby(
            ['tsa', 'au_id', 'ifm', 'curve_id']
        ):
            f.write(f'*Y ? {ifm} {au_id} ? ?\n')
            f.write('_AGE totvol\n')
            for _, row in group.sort_values('age').iterrows():
                f.write(f"{int(row['age'])} {row['volume']:.6f}\n")
            f.write('\n')

    with open(WOODSTOCK_DIR / f'{MODEL_NAME}.act', 'w') as f:
        f.write('*ACTION harvest Y\n')
        f.write('*OPERABLE harvest\n')
        f.write(f'? ? ? ? ? _AGE >= {MIN_HARVEST_AGE} and _AGE <= {MAX_HARVEST_AGE}\n')

    with open(WOODSTOCK_DIR / f'{MODEL_NAME}.trn', 'w') as f:
        f.write('*CASE harvest\n')
        f.write('*SOURCE ? ? ? ? ?\n')
        f.write('*TARGET ? ? ? ? ? 100 _AGE 0\n')
    timings['write_files'] = toc(t0, 'Write Woodstock files')

    t0 = tic('Load model from Woodstock files')
    model = ws3.forest.ForestModel(
        model_name=MODEL_NAME,
        model_path=str(WOODSTOCK_DIR),
        base_year=2026,
        horizon=HORIZON,
        period_length=PERIOD_LENGTH,
        max_age=MAX_AGE,
    )
    model.import_landscape_section()
    model.import_areas_section()
    model.import_yields_section()
    model.import_actions_section()
    model.import_transitions_section()
    model.compile_actions()
    model.reset()
    print(f'DTs: {len(model.dtypes)}, total area: {model.inventory(period=0):.1f} ha')
    timings['load_model'] = toc(t0, 'Load model from Woodstock files')

    t0 = tic('Set up LP problem')
    import functools

    model.add_null_action()
    # Allow null-action paths to grow past MAX_AGE so full-horizon trees exist.
    # Initial fragment ages can exceed MAX_AGE (up to ~436), and unharvested
    # stands age through the horizon. Curves default to xmax=1000 and extend
    # the last yield value, so lookups at ages > 300 remain valid.
    max_initial_age = int(fragments['F_AGE'].max())
    null_max_age = max_initial_age + HORIZON * PERIOD_LENGTH
    null_oe = f'_age >= 0 and _age <= {null_max_age}'
    wildcard_mask = tuple(['?' for _ in range(model.nthemes())])
    model.oper_expr['null'] = {wildcard_mask: null_oe}
    for dt in model.dtypes.values():
        dt._max_age = null_max_age  # raise operability upper bound
        dt.oper_expr['null'] = [null_oe]
        # clear any previously compiled null operability so it recompiles with new bounds
        dt.operability.pop('null', None)

    model.reset_actions()
    model.actions['harvest'].is_harvest = True

    # Debug: verify null action is operable at the maximum required age
    bad = []
    for dtk, dt in model.dtypes.items():
        if not dt.is_operable('null', 1, null_max_age):
            bad.append((dtk, dt.operability.get('null')))
    if bad:
        print(f'WARNING: null action not operable at age {null_max_age} for:', bad[:3])

    def cmp_c_z(fm, path, expr):
        result = 0.0
        for t, n in enumerate(path, start=1):
            d = n.data()
            if fm.is_harvest(d['acode']):
                result += fm.compile_product(
                    t, expr, d['acode'], [d['dtk']], d['age'], coeff=False
                )
        return result

    def cmp_c_caa(fm, path, expr, acodes, mask=None):
        result = {}
        for t, n in enumerate(path, start=1):
            d = n.data()
            if mask and not fm.match_mask(mask, d['dtk']):
                continue
            if d['acode'] in acodes:
                result[t] = fm.compile_product(
                    t, expr, d['acode'], [d['dtk']], d['age'], coeff=False
                )
        return result

    expr = 'totvol'
    coeff_funcs = {'z': functools.partial(cmp_c_z, expr=expr)}
    coeff_funcs['cflw_hv'] = functools.partial(
        cmp_c_caa, expr='totvol', acodes=['harvest']
    )
    cflw_e = {'cflw_hv': ({p: 0.05 for p in model.periods}, 1)}

    problem = model.add_problem(
        name='evenflow-max-hv-managed',
        coeff_funcs=coeff_funcs,
        cflw_e=cflw_e,
        cgen_data=None,
        acodes=('null', 'harvest'),
        sense=ws3.opt.SENSE_MAXIMIZE,
        mask=('?', 'managed', '?', '?', '?'),
        workers=WORKERS,
        verbose=True,
    )
    timings['setup_problem'] = toc(t0, 'Set up LP problem')

    print(f'Problem columns: {len(problem._vars):,}')
    print(f'Problem rows: {len(problem._constraints):,}')

    t0 = tic('Solve LP')
    problem.solve(verbose=False)
    timings['solve'] = toc(t0, 'Solve LP')
    print('Status:', problem.status())
    print('Objective value (total m3):', problem.z())

    t0 = tic('Compile and apply schedule')
    schedule = model.compile_schedule(problem)
    model.reset()
    model.apply_schedule(
        schedule,
        force_integral_area=False,
        override_operability=False,
        fuzzy_age=False,
        recourse_enabled=False,
        verbose=False,
        compile_c_ycomps=True,
    )
    timings['schedule'] = toc(t0, 'Compile and apply schedule')

    t0 = tic('Compile results')
    opt_results = pd.DataFrame({
        'period': model.periods,
        'harvest_area_ha': [
            model.compile_product(p, '1.', acode='harvest') for p in model.periods
        ],
        'harvest_volume_m3': [
            model.compile_product(p, 'totvol', acode='harvest') for p in model.periods
        ],
        'growing_stock_m3': [
            model.inventory(p, 'totvol') for p in model.periods
        ],
    })
    timings['compile_results'] = toc(t0, 'Compile results')

    print('\nOptimization-based even-flow harvest scenario')
    print(f'Total harvested area (periods 1-{HORIZON}): {opt_results["harvest_area_ha"].sum():.1f} ha')
    print(f'Total harvested volume (periods 1-{HORIZON}): {opt_results["harvest_volume_m3"].sum():.0f} m3')
    print(f'Mean harvest volume per period: {opt_results["harvest_volume_m3"].mean():.0f} m3')
    print(f'Mean annual harvest volume: {opt_results["harvest_volume_m3"].mean() / PERIOD_LENGTH:.0f} m3/yr')
    print('\nFirst 10 periods:')
    print(opt_results.head(10).to_string(index=False))
    print('\nLast 5 periods:')
    print(opt_results.tail(5).to_string(index=False))

    print('\n=== TIMING SUMMARY ===')
    total = sum(timings.values())
    for k, v in timings.items():
        print(f'{k:25s}: {v:7.2f}s ({100*v/total:5.1f}%)')
    print(f'{"TOTAL":25s}: {total:7.2f}s')

    return timings, opt_results


if __name__ == '__main__':
    pr = cProfile.Profile()
    pr.enable()
    try:
        timings, opt_results = main()
    finally:
        pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(30)
    print('\n=== CPROFILE TOP 30 (cumulative) ===')
    print(s.getvalue())
