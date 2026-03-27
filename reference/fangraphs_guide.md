# FanGraphs Data Guide

## REST API

FanGraphs has an undocumented REST API that mirrors the projections UI. All projection data is available at:

```
https://www.fangraphs.com/api/projections?type={TYPE}&stats={STATS}&pos=all&team=0&players=0&lg=all
```

Returns JSON array. Each object has the same columns as the CSV export. Every record includes `xMLBAMID` and `playerid` (FanGraphs internal ID).

### Parameters

| Parameter | Values | Notes |
|-----------|--------|-------|
| `type` | See type table below | Required |
| `stats` | `bat`, `pit` | Required |
| `pos` | `all`, `c`, `1b`, `2b`, `ss`, `3b`, `of`, `dh` | Optional filter |
| `team` | `0` (all), or team ID | Optional filter |
| `players` | `0` (all) | Required |
| `lg` | `all`, `al`, `nl` | Optional filter |

### Projection Type Parameters

#### Pre-Season Projections (2026)
| Type | System | Notes |
|------|--------|-------|
| `steamer` | Steamer | Exhaustive (4187 bat / 5162 pit). Includes quantile columns (q10-q90) for `statgroup=percentile`. |
| `atc` | ATC | Consensus blend (627 bat / 844 pit). Curated to MLB-relevant pool. |
| `zips` | ZiPS | Dan Szymborski system (1903 bat / 1838 pit). |
| `fangraphsdc` | Depth Charts | Manual playing-time overlay on projections (637 bat / 810 pit). |
| `thebat` | THE BAT | Derek Carty system (693 bat / 708 pit). |
| `thebatx` | THE BAT X | Playing-time adjusted BAT. Uses decimal PA values (e.g., 637.46) reflecting injury-probability-weighted expected playing time. Key file for playing time uncertainty analysis. |
| `oopsy` | OOPSY | Uses Depth Charts playing time (2803 bat / 4248 pit). |
| `oopsypeak` | OOPSY Peak | Uses neutral/peak playing time (2865 bat / 4256 pit). Members exclusive. |

#### 600 PA / 200 IP Projections
| Type | System | Notes |
|------|--------|-------|
| `steamer600` | Steamer 600 | Full-season rate baseline (4187 bat / 5162 pit). Compare with regular Steamer to isolate playing-time discount. |

#### 3-Year Projections (ZiPS only)
| Type | System | Notes |
|------|--------|-------|
| `zipsp1` | ZiPS 3yr 2027 | 2027 projections with aging curves (1903 bat / 1838 pit). |
| `zipsp2` | ZiPS 3yr 2028 | 2028 projections (1903 bat / 1838 pit). |

**IMPORTANT**: `&season=2027` or `&season=2028` does NOT work — returns identical 2026 data. Use the `zipsp1`/`zipsp2` type parameters instead.

#### Platoon Splits (Steamer, Members Exclusive)
| Type | System | Notes |
|------|--------|-------|
| `steamer_vl_0` | Steamer vs LHP (batters) | Batter projections vs left-handed pitching. Batter data ONLY regardless of `stats` param. |
| `steamer_vr_0` | Steamer vs RHP (batters) | Batter projections vs right-handed pitching. Batter data ONLY regardless of `stats` param. |

**CRITICAL**: The split types (`steamer_vl_0`, `steamer_vr_0`) return BATTER data even when `stats=pit` is specified. Pitcher platoon splits (vs LHB / vs RHB) do NOT appear to be available via this API mechanism. The `&hand=L` / `&hand=R` parameters also do NOT produce real splits — they return identical data to the base Steamer projection.

#### Updated In-Season Projections (RoS)
| Type | System | Notes |
|------|--------|-------|
| `rfangraphsdc` | Depth Charts RoS | Rest-of-season. Only available during the season. |
| `rsteamer` | Steamer RoS | |
| `rzips` | ZiPS RoS | |
| `rzipsdc` | ZiPS DC RoS | |
| `rthebat` | THE BAT RoS | |
| `rthebatx` | THE BAT X RoS | |
| `ratcdc` | ATC DC RoS | |
| `roopsy` | OOPSY DC RoS | |

Note: RoS types are prefixed with `r`. These may return empty arrays before the season starts.

### Stat Groups (for Steamer quantile data)

The default API call returns the "Dashboard" stat group. To get quantile columns (q10, q20, ... q90), use the UI endpoint with `statgroup=percentile`. The API endpoint does not directly support this — you need to use the full page URL:

```
https://www.fangraphs.com/projections?type=steamer&stats=bat&pos=all&team=0&players=0&lg=all&statgroup=percentile
```

Then use the "Export Data" link on the page, or extract from `__NEXT_DATA__`.

### Quantile Interpretation

Steamer quantile columns (q10-q90) represent:
- **Batters**: wOBA quantiles (q10 = low/bad, q90 = high/good)
- **Pitchers**: ERA quantiles (q10 = high/bad, q90 = low/good)

These are NOT per-stat quantiles. They are composite performance metric distributions. To convert to WERTH sigma, regress total_werth on the performance metric across starters and multiply by `(q90 - q10) / 2.56 × sqrt(PA_or_IP / avg)`.

## Architecture Notes

FanGraphs uses Next.js with React Query. Key technical details:

- Initial data is embedded in `__NEXT_DATA__` script tag as dehydrated React Query state
- The projections page loads data lazily — you must scroll to the table to trigger data loading before the "Export Data" link works
- Column naming varies by projection system: most use `PlayerName`, but THE BAT X uses `Name` (with BOM prefix `\ufeffName`)
- All projection CSVs include `xMLBAMID` for cross-system joins

## Bulk Download Pattern

### Via Browser Console (JavaScript)

```javascript
async function downloadProjection(type, stats, filename) {
  const url = `/api/projections?type=${type}&stats=${stats}&pos=all&team=0&players=0&lg=all`;
  const resp = await fetch(url);
  const data = await resp.json();
  const cols = Object.keys(data[0]);
  const header = cols.join(',');
  const rows = data.map(row => cols.map(c => {
    const val = row[c];
    if (val === null || val === undefined) return '';
    if (typeof val === 'string' && (val.includes(',') || val.includes('"')))
      return '"' + val.replace(/"/g, '""') + '"';
    return val;
  }).join(','));
  const csv = '\uFEFF' + header + '\n' + rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  return { file: filename, records: data.length, cols: cols.length };
}

// Example usage:
await downloadProjection('steamer', 'bat', 'FanGraphs_Steamer_Batters_2026.csv');
await downloadProjection('atc', 'pit', 'FanGraphs_ATC_Pitchers_2026.csv');
```

**WARNING**: Chrome may silently block blob URL downloads after ~15-20 rapid downloads in a session. If this happens:
1. Open a new browser tab and retry from there
2. Space downloads with 2-second delays between each
3. If still blocked, use the native "Export Data" link on the projections page instead
4. Data URI (`data:text/csv,...`) downloads may also be blocked in the same session

### Via Python (direct HTTP, if network allows)

```python
import json, csv, urllib.request

def download_projection(proj_type, stats, filename):
    url = f'https://www.fangraphs.com/api/projections?type={proj_type}&stats={stats}&pos=all&team=0&players=0&lg=all'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    cols = list(data[0].keys())
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        writer.writerows(data)
    return len(data), len(cols)
```

Note: This requires direct internet access to fangraphs.com — will not work from sandboxed VMs.

## Data Inventory (as of 2026-03-22)

### Files in `existing-tools/`

| File | System | Rows | Cols | Key Use |
|------|--------|------|------|---------|
| FanGraphs_Steamer_Batters_2026.csv | Steamer | 4187 | 80 | Primary projection + quantiles (q10-q90) |
| FanGraphs_Steamer_Pitchers_2026.csv | Steamer | 5162 | 68 | Primary projection + quantiles |
| FanGraphs_ATC_Batters_2026.csv | ATC | 627 | 63 | Consensus blend, curated pool |
| FanGraphs_ATC_Pitchers_2026.csv | ATC | 844 | 53 | Consensus blend, curated pool |
| FanGraphs_TheBatX_Batters_2026.csv | THE BAT X | 693 | 74 | Playing time uncertainty (decimal PA) |
| FanGraphs_TheBatX_Pitchers_2026.csv | THE BAT X | 713 | 69 | Playing time uncertainty (decimal IP) |
| FanGraphs_TheBat_Batters_2026.csv | THE BAT | 693 | 57 | Rate-only (no PT adjustment) |
| FanGraphs_TheBat_Pitchers_2026.csv | THE BAT | 708 | 47 | Rate-only |
| FanGraphs_DepthCharts_Batters_2026.csv | Depth Charts | 637 | 57 | Manual playing time overlay |
| FanGraphs_DepthCharts_Pitchers_2026.csv | Depth Charts | 810 | 47 | Manual playing time overlay |
| FanGraphs_ZiPS_Batters_2026.csv | ZiPS | 1903 | 57 | Dan Szymborski system |
| FanGraphs_ZiPS_Pitchers_2026.csv | ZiPS | 1838 | 46 | Dan Szymborski system |
| FanGraphs_ZiPSDC_Batters_2026.csv | ZiPS DC | 637 | 57 | ZiPS + Depth Charts PT |
| FanGraphs_ZiPSDC_Pitchers_2026.csv | ZiPS DC | 810 | 46 | ZiPS + Depth Charts PT |
| FanGraphs_Steamer600_Batters_2026.csv | Steamer 600 | 4187 | 57 | Full-season rate baseline |
| FanGraphs_Steamer600_Pitchers_2026.csv | Steamer 600 | 5162 | 46 | Full-season rate baseline |
| FanGraphs_OOPSY_Batters_2026.csv | OOPSY | 2803 | 57 | DC playing time |
| FanGraphs_OOPSY_Pitchers_2026.csv | OOPSY | 4248 | 47 | DC playing time |
| FanGraphs_OOPSYPeak_Batters_2026.csv | OOPSY Peak | 2865 | 57 | Neutral/peak PT (Members exclusive) |
| FanGraphs_OOPSYPeak_Pitchers_2026.csv | OOPSY Peak | 4256 | 47 | Neutral/peak PT (Members exclusive) |
| FanGraphs_Steamer_Batters_vsLHP_2026.csv | Steamer Splits | 4187 | 76 | Batter projections vs LHP |
| FanGraphs_Steamer_Batters_vsRHP_2026.csv | Steamer Splits | 4187 | 76 | Batter projections vs RHP |
| FanGraphs_ZiPS3yr_Batters_2027.csv | ZiPS 3yr | 1903 | 57 | Keeper analysis: 2027 aging curves |

### Files NOT Yet Downloaded (need browser session)

| File | API Call | Notes |
|------|----------|-------|
| FanGraphs_ZiPS3yr_Pitchers_2027.csv | `type=zipsp1&stats=pit` | 1838 rows, 46 cols |
| FanGraphs_ZiPS3yr_Batters_2028.csv | `type=zipsp2&stats=bat` | 1903 rows, 57 cols |
| FanGraphs_ZiPS3yr_Pitchers_2028.csv | `type=zipsp2&stats=pit` | 1838 rows, 46 cols |
| Steamer Pitcher Splits vs LHB | Unknown type param | Not available via `steamer_vl_0` with `stats=pit` |

To download missing files: navigate to FanGraphs in browser, open console, and use the `downloadProjection()` function above with appropriate type/stats params. Do this in a fresh browser session to avoid Chrome's download throttle.

## Playing Time Analysis

Cross-system PA comparison reveals injury risk consensus:

| System | What PA Represents | Example (Acuña) |
|--------|-------------------|-----------------|
| Steamer 600 | Full-season rate baseline | 600 PA |
| THE BAT X | Injury-probability-weighted expected PA | 629 PA |
| Depth Charts | Manually curated expected PA | 651 PA |
| Steamer | Statistical expected PA | 676 PA |

**THE BAT X is the key file for playing time uncertainty**. Its decimal PA values (e.g., 637.46 instead of 637) reflect continuous injury probability modeling. Comparing THE BAT X PA to Steamer 600 PA isolates the playing time discount for each player.

**Steamer quantiles model performance uncertainty**, not playing time. The q10-q90 columns represent wOBA (batters) or ERA (pitchers) outcome distributions at the projected playing time.

## Splits Analysis

Real platoon splits use `steamer_vl_0` (vs LHP) and `steamer_vr_0` (vs RHP) type parameters. Example:

| Player | vs LHP | vs RHP | Platoon Gap |
|--------|--------|--------|-------------|
| Judge | .483 OBP, 158 PA | .392 OBP, 475 PA | +.091 OBP vs LHP |

The PA split reflects expected plate appearances against each handedness. These are useful for identifying:
- Platoon-dependent hitters (large gap = risky if team faces lots of same-hand pitching)
- Matchup exploitation opportunities in H2H weekly leagues
