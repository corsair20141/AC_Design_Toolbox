# Propeller Data Reference Area

This directory is the recommended local landing zone for third-party propeller
data used with `ac_design_toolbox.propulsion.data` parsers. Keep raw vendor or
university files separate from generated summaries so source provenance remains
clear.

Suggested layout:

```text
data/propellers/
  raw/
    uiuc/
      UIUC-propDB.zip
      DATA/
      volume-1/
      volume-2/
      volume-3/
      volume-4/
    apc/
      PERFILES_WEB-YYYYMM.zipx
      PERFILES_WEB-YYYYMM/
      PE0-FILES_WEB-YYYYMM.zipx
      PE0-FILES_WEB-YYYYMM/
  processed/
```

## UIUC Propeller Database

Source page:

```text
https://m-selig.ae.illinois.edu/props/propDB.html
```

The UIUC page provides an `UIUC-propDB.zip` archive containing all volumes.
Download it into `data/propellers/raw/uiuc/` and extract the archive contents
directly there, so the volume folders sit immediately under `raw/uiuc/`.
For cleaner parser lookup, collect the `.txt` files from the volume `data/`
folders into a flat `data/propellers/raw/uiuc/DATA/` folder. Keeping the plots,
photos, papers, and HTML in their original folders is fine.

The parser expects wind-tunnel coefficient files that look like:

```text
J CT CP eta
0.162 0.0980 0.0465 0.342
...
```

Use:

```python
from ac_design_toolbox.propulsion import load_uiuc_performance_file

propeller = load_uiuc_performance_file(
    "data/propellers/raw/uiuc/DATA/apcsf_9x4.7_kt1033_4008.txt"
)
```

Static UIUC files with `RPM CT CP` are intentionally rejected by the parser
because the current `TabulatedPropeller` model expects CT/CP as a function of
advance ratio.

## APC Performance Data

Performance data page:

```text
https://www.apcprop.com/technical-information/performance-data/
```

Downloads page:

```text
https://www.apcprop.com/technical-information/file-downloads/
```

Download the latest APC performance archive, named like
`PERFILES_WEB-YYYYMM.zipx`, into `data/propellers/raw/apc/` and extract it
there. APC `PER3_*.dat` files contain one or more blocks like:

```text
PROP RPM = 1000
V J Pe Ct Cp ...
...
```

Use:

```python
from ac_design_toolbox.propulsion import load_apc_performance_file, load_apc_table_for_rpm

table_set = load_apc_performance_file(
    "data/propellers/raw/apc/PERFILES_WEB-YYYYMM/PER3_10x5E.dat"
)
propeller = load_apc_table_for_rpm(
    "data/propellers/raw/apc/PERFILES_WEB-YYYYMM/PER3_10x5E.dat",
    5000.0,
    nearest=True,
)
```

APC also publishes geometry archives named like `PE0-FILES_WEB-YYYYMM.zipx`.
Those `.peo` geometry files are not consumed by the current coefficient-table
parser, but storing them beside the performance archive is useful for later
geometry-aware adapters.

## Repo Inclusion Guidance

Before committing downloaded third-party archives, check license/provenance and
file size. For day-to-day studies, it is usually better to keep raw downloads
local under this directory and commit only small derived examples or tests.
If full archive inclusion is desired later, add a short provenance note with:

- source URL
- download date
- original archive name
- checksum if available
- any extraction or filtering performed
