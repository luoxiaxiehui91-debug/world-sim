import os
import csv, sys, collections, statistics

PATH = os.environ.get("GED_CSV_PATH", "")

rows = 0
header = None
type_viol = collections.Counter()
year_min, year_max = 9999, 0
country_ct = collections.Counter()
region_ct = collections.Counter()
deaths_best_sum = collections.Counter()      # by type
deaths_best_gt0 = collections.Counter()
n_with_deaths_field = 0
# deaths by year (best) for time series sanity
deaths_year = collections.Counter()
events_year = collections.Counter()
# precision flags
date_prec = collections.Counter()
where_prec = collections.Counter()
n_sources_dist = collections.Counter()
# one-sided / non-state etc geographic spread
lat_ok = 0

with open(PATH, "r", encoding="utf-8", errors="replace", newline="") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        if len(row) != len(header):
            # safety
            continue
        d = dict(zip(header, row))
        rows += 1
        tv = d.get("type_of_violence", "").strip()
        type_viol[tv] += 1
        try:
            y = int(d.get("year", "").strip())
            year_min = min(year_min, y)
            year_max = max(year_max, y)
            events_year[y] += 1
        except:
            pass
        c = d.get("country", "").strip()
        if c:
            country_ct[c] += 1
        rg = d.get("region", "").strip()
        if rg:
            region_ct[rg] += 1
        # deaths
        try:
            db = float(d.get("best", "").strip() or "0")
        except:
            db = 0.0
        if d.get("best", "").strip():
            n_with_deaths_field += 1
            deaths_best_sum[tv] += db
            if db > 0:
                deaths_best_gt0[tv] += 1
            try:
                yy = int(d.get("year","").strip())
                deaths_year[yy] += db
            except: pass
        # precision
        date_prec[d.get("date_precision","").strip()] += 1
        where_prec[d.get("where_prec","").strip()] += 1
        try:
            ns = int(d.get("number_of_sources","").strip() or "0")
            n_sources_dist[ns] += 1
        except: pass
        try:
            lat = float(d.get("latitude","").strip() or "0")
            if lat != 0.0:
                lat_ok += 1
        except: pass

print("=== GED v26.1 EMPIRICAL PROFILE ===")
print(f"events (rows)        : {rows}")
print(f"columns              : {len(header)}")
print(f"year range           : {year_min} - {year_max}")
print(f"events with best>0   : {deaths_best_gt0.total() } / deaths_field_present={n_with_deaths_field}")
print(f"lat != 0 (geolocated): {lat_ok} ({100*lat_ok/rows:.1f}%)")
print()
print("type_of_violence distribution:")
for k in sorted(type_viol):
    print(f"  type {k!r}: {type_viol[k]:>8}  ({100*type_viol[k]/rows:.1f}%)  deaths_best_sum={deaths_best_sum[k]:.0f}  events_deaths>0={deaths_best_gt0[k]}")
print()
print("region distribution (top):")
for k,v in region_ct.most_common(12):
    print(f"  {k!r}: {v}")
print()
print("top 15 countries by event count:")
for k,v in country_ct.most_common(15):
    print(f"  {k!r}: {v}")
print()
print("date_precision dist:", dict(date_prec))
print("where_prec dist    :", dict(where_prec))
print("number_of_sources dist (top):", dict(n_sources_dist.most_common(8)))
print()
print("events per 5-year bucket:")
buckets = collections.Counter()
for y,c in events_year.items():
    b = (y//5)*5
    buckets[b]+=c
for b in sorted(buckets):
    print(f"  {b}-{b+4}: {buckets[b]}")
print()
print("total best deaths sum:", sum(deaths_best_sum.values()))
