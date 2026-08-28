# Runbook: TIPSY (BTC) replant curves on Linux + Wine (tsa29mini)

Purpose: regenerate the species-switching replant yield curves
(`data/tipsy_curves_tsa29mini_replant.csv`) for fresh-fuchs phase P6.
See `data/tipsy_replant_run_manifest.json` for the recorded run
provenance and validation evidence.

## Why this runbook exists

The earlier UBC-FRESH Wine lane evidence (2026-08-09, full tsa29) relied
on a pre-built wine prefix (`~/.wine-tipsy64`) and system `xvfb-run`,
both of which may be absent on a fresh host. This lane is
self-contained: a scratch wine prefix with wine-mono, and a userspace
Xvfb (no root, no system packages). All scratch state lives under
`tipsy_io/scratch/` (gitignored).

## Prerequisites

- `/usr/bin/wine` (wine64-capable; wine32 NOT required — TIPSYbtc.exe is
  a 64-bit .NET assembly).
- Network access to dl.winehq.org (wine-mono MSI) and archive.ubuntu.com
  (Xvfb debs), one-time setup only.
- This repo's `data/model_input_bundle/au_table.csv` and the parent
  tsa29 instance's `data/03_input-tsa29.csv` (SI source).

## One-time lane setup

```bash
I=<instance root>
mkdir -p $I/tipsy_io/scratch/{work,btc_install}

# 1. Stage a writable BTC install (copy any known-good TIPSY 4.7 BTC
#    install tree, e.g. from the UBC-FRESH integration evidence).
cp -r <known-good btc_install>/* $I/tipsy_io/scratch/btc_install/

# 2. Wine prefix + wine-mono (required: TIPSYbtc.exe is .NET).
export WINEPREFIX=$I/tipsy_io/scratch/wineprefix WINEDEBUG=-all
curl -sL -o $I/tipsy_io/scratch/wine-mono-9.0.0-x86.msi \
  https://dl.winehq.org/wine/wine-mono/9.0.0/wine-mono-9.0.0-x86.msi
wine msiexec /i "Z:$(echo $I/tipsy_io/scratch/wine-mono-9.0.0-x86.msi | sed 's|/|\\|g')" /qn

# 3. Userspace Xvfb (BTC creates windows even in /TSR unattended mode).
mkdir -p $I/tipsy_io/scratch/xvfb/debs && cd $I/tipsy_io/scratch/xvfb/debs
apt-get download xvfb libxfont2 xserver-common x11-xkb-utils xkb-data
cd .. && for d in debs/*.deb; do dpkg -x "$d" rootfs; done
# Xvfb invokes xkbcomp and resolves xkb data via compiled-in absolute
# paths; patch the binary strings to a writable mirror (same lengths):
#   /usr/bin\x00 -> /tmp/xkb\x00 ; /usr/share/X11/xkb -> /tmp/xkb/share/xkb ;
#   /var/lib/xkb/ -> /tmp/xkb/out/
# (see the P6.6 closeout / issue UBC-FRESH/fresh-fuchs#48 for the patch snippet)
mkdir -p /tmp/xkb/out
cp rootfs/usr/bin/xkbcomp /tmp/xkb/xkbcomp
ln -sf $I/tipsy_io/scratch/xvfb/rootfs/usr/share/X11/xkb /tmp/xkb/share/xkb
```

## Regenerate the curves

```bash
I=<instance root>
cd $I
.venv/bin/python build_replant_tipsy_input.py \
  --tsa29-input ../femic-tsa29-instance/data/03_input-tsa29.csv

export LD_LIBRARY_PATH=$I/tipsy_io/scratch/xvfb/rootfs/usr/lib/x86_64-linux-gnu
/tmp/xkb/Xvfb-patched :99 -screen 0 1024x768x16 & XVFB_PID=$!
export DISPLAY=:99 WINEPREFIX=$I/tipsy_io/scratch/wineprefix WINEDEBUG=-all
cd $I/tipsy_io/scratch/work
cp $I/data/03_input-tsa29mini-replant.csv .
wine $I/tipsy_io/scratch/btc_install/TIPSYbtc.exe /TSR \
  03_input-tsa29mini-replant.csv 04_output-tsa29mini-replant.csv 04_error-tsa29mini-replant.csv
kill $XVFB_PID

# Parse to long-format curves (femic):
$I/.venv/bin/python -c "
import pandas as pd
from femic.pipeline.tipsy import parse_btc_tsr_transposed_output
curves = parse_btc_tsr_transposed_output(output_csv='04_output-tsa29mini-replant.csv', pd_module=pd)
curves.to_csv('$I/data/tipsy_curves_tsa29mini_replant.csv', index=False)
"
cp 04_output-tsa29mini-replant.csv 04_error-tsa29mini-replant.csv $I/data/
```

## Acceptance checks (recorded in the run manifest)

- exit code 0; `04_error` has zero data rows.
- curves cover all 63 feature_ids x 36 ages (0..350).
- L <= M <= H max-yield ordering per stratum x species (SW inherits the
  parent instance's M>H inversions verbatim — see manifest).
- SW replant curves for SBPS_SX are bit-identical to the parent tsa29
  native SW curves (regime identity check).
