# Fantasy Baseball Draft Tool Research

## 1. Executive Summary

**Five key findings that should drive our tool design:**

1. **Mr. Cheatsheet already supports all 12 of our league categories** (R/HR/TB/RBI/SBN/OBP + K/QS/ERA/WHIP/K÷BB/SVHD). Its WERTH system is a z-score methodology with 23 hitting and 27 pitching category options, category weighting, and position-specific replacement level. We should build *on top of* its proven approach rather than from scratch.

2. **WERTH is a z-score system, not SGP — and that's the right choice for H2H categories.** SGP was designed for roto and won the FanGraphs "Great Valuation System Test," but it requires historical standings data and measures cumulative season-long standings movement. Z-scores are better suited to H2H because they measure relative player strength without needing roto-specific calibration data.

3. **Rate stat handling is the hardest valuation problem, and Mr. Cheatsheet solves it well.** It converts rate stats (OBP, ERA, WHIP, K/BB) into "counting equivalents" that account for playing time. A .400 OBP in 200 PA is worth less than a .350 OBP in 600 PA. This marginal-team-impact approach is critical for our league's 4 rate-stat categories.

4. **8-team leagues compress replacement level dramatically.** With only 8 teams, the replacement-level player at every position is already very good. This means: (a) positional scarcity matters less, (b) elite talent is more differentiating, (c) rate stats become more important since the counting-stat floor is high, and (d) the waiver wire is deep, making streaming viable.

5. **The FanGraphs projection CSVs have everything we need.** Both Steamer and ATC projections include all component stats for our 12 categories. TB, SBN, and SVHD require trivial arithmetic (1B+2×2B+3×3B+4×HR, SB-CS, SV+HLD). The SFBB ID map bridges FanGraphs player IDs to ESPN IDs via MLBAM ID as the reliable join key.

---

## 2. Mr. Cheatsheet Deep Dive

### 2.1 Architecture Overview

The spreadsheet has 26 sheets organized in a pipeline:

```
Settings (user config)
  → Guts-1/Guts-2 (category mapping, weights, roster math)
  → Projection-H / Projection-P (10 projection sources per player type)
  → Pre (position eligibility engine)
  → Filter-H / Filter-P (starter pool, rate stat conversion, means/stdevs)
  → All-WERTH (per-category z-scores → total WERTH → position-adjusted WERTH)
  → Your Roto Draft (draft-day UI with VBA click-to-draft)
  → Draft Log / Standings / Rosters (draft tracking and projections)
```

**Key design decision**: ALL valuation math is in Excel formulas, not VBA. VBA handles only UI interactions (click-to-draft, search, notes popup, settings save/load). This means the entire valuation engine is transparent and traceable through cell references.

### 2.2 The Complete WERTH Formula Chain

#### Step 1: Projection Selection / Blending

10 projection sources are available: THE BAT, Steamer, ZiPS, FanGraphs DC, Clay Davenport, Steamer-600, OOPSY, Marcel, Average of Base, and Mr. Cheatsheet's Blend. Users can also create a custom weighted combination or import their own.

**Custom Combination formula** (`Projection-H!EZ2`):
```
For each source i (1-10):
  IF weight_i > 0: (weight_i / 100) × source_i_stat
Result = SUM of all weighted contributions
```
Weights are configured in `Settings!R23:R32` → `Guts-2!H1:H10` and must sum to 100.

#### Step 2: Starter Pool Identification

For each position, the number of "starters" = `roster_slots × num_teams`. Example: 12-team league with 1 C slot → 12 catchers are starters. Players are flagged Yes/No in `Filter-H!B2` based on whether they fall within the starter pool.

**Formula for starter count per position** (`Filter-H!AR4`):
```
AR4 = AQ4 × AR2
where AQ4 = slots at position (from Settings!G4), AR2 = num_teams (from Settings!K4)
```

#### Step 3: Rate Stat Conversion to Counting Equivalents

This is the most important step. Rate stats are converted so they can be z-scored alongside counting stats.

**Hitting rate stats** (e.g., AVGc in `Filter-H!V2`):
```
AVGc = ((player_AVG × player_AB) - (league_avg_AVG × player_AB)) / (avg_starter_AB × total_starter_slots)
```
Where:
- `league_avg_AVG` = SUM(all_starter_Hits) / SUM(all_starter_AB)
- `avg_starter_AB` = AVERAGEIF(starters, AB)
- `total_starter_slots` = SUM of all hitting position slots

**Interpretation**: This measures "marginal hits above average, scaled by playing time share." It answers: "If I replace an average starter with this player, how much does my team's batting average change?" A high-OBP player with low PA contributes less than a moderate-OBP player with high PA.

**Pitching rate stats** (e.g., ERAc in `Filter-P!AC2`):
```
ERAc = ((player_IP / total_league_IP) × player_ERA + (1 - player_IP/total_league_IP) × league_ERA) - league_ERA
```
**Interpretation**: This is an innings-weighted marginal contribution. It asks: "If this pitcher replaced league-average innings on my team, how much would my team ERA change?" Pitchers with fewer IP get regressed toward the league mean — a brilliant design that naturally handles the SP vs RP valuation problem.

The same pattern applies to WHIPc, K/9c, BAAc, and K/BBc.

**Guts-1 column M** controls which conversion to use:
- M=1: Counting stat (use raw value)
- M=2: Rate stat like AVG/OBP/SLG/BAA (marginal counting conversion)
- M=3: K/9, K/BB (different rate conversion)
- M=4: ERA, WHIP (IP-weighted rate conversion)

#### Step 4: Mean and Standard Deviation of Starter Pool

For each category, computed across all projected starters:
```
Mean = AVERAGEIF(starters, stat)
StDev = STDEV(IF(starters, stat))
```

For "lower is better" stats (ERA, WHIP, CS, K's allowed), the StDev is **negated** so that z-score direction is correct (negative z-score = bad for the fantasy manager).

Stored in `Filter-H!AQ` (means) and `Filter-H!AR` (stdevs), rows 20-51.

#### Step 5: Per-Category WERTH (the z-score)

The core formula (`All-WERTH!S4`):
```excel
=IFERROR(IF(S$1="","",
  ((VLOOKUP($O4, 'Filter-H'!$A$2:$BB$584,
      VLOOKUP(S$1,'Guts-1'!$A$1:$D$25,4,FALSE), FALSE)
    - CHOOSE(MATCH(S$1,'Guts-1'!$A$1:$A$25,0),
        'Filter-H'!$AQ$36, 'Filter-H'!$AQ$26, ...)
  ) / CHOOSE(MATCH(S$1,'Guts-1'!$A$1:$A$25,0),
        'Filter-H'!$AR$36, 'Filter-H'!$AR$26, ...)
  ) * VLOOKUP(S$1,'Guts-1'!$A$1:$B$25,2,FALSE)
), "")
```

**Breaking this down:**
1. `VLOOKUP(player, Filter-H, column, FALSE)` — gets the player's stat value (using the converted column for rate stats)
2. `CHOOSE(MATCH(...))` for mean — gets the replacement-level mean for that category
3. Division by StDev — converts to z-score
4. `× VLOOKUP(category, Guts-1, weight)` — multiplies by category weight (1.0 for Full, 0.5 for Half, 0 if not selected)

**For rate stats**: The formula automatically uses the "c" (converted) column via Guts-1 column D mapping. AVG maps to column 22 (AVGc) instead of column 16 (raw AVG).

#### Step 6: Total WERTH

```
HIT-WERTH = SUM(columns S through AD)    — up to 12 hitting categories
PIT-WERTH = SUM(columns AE through AP)   — up to 12 pitching categories
Total WERTH (column AQ) = HIT-WERTH + PIT-WERTH
```
If total is zero (no categories match), set to -1000 to sort to bottom.

#### Step 7: Position-Adjusted WERTH (the final ranking value)

```excel
=IFERROR(
  IF(OR($A4="RP",$A4="SP"),
    ABS(INDEX('Filter-P'!$AR$4:$AR$6, MATCH($A4,'Filter-P'!$AN$4:$AN$6,0))) + AQ4,
    ABS(INDEX('Filter-H'!$AW$4:$AW$15, MATCH($A4,'Filter-H'!$AP$4:$AP$15,0))) + AQ4
      + IF(Pre!$CB4<>"", 0.5, 0)
  ), "")
```

**What this does:**
1. Gets the replacement-level WERTH for the player's position (a negative number)
2. Takes the absolute value
3. Adds it to the player's total WERTH
4. Adds +0.5 bonus for multi-position eligibility

**Why this works**: Scarce positions (C, SS) have more negative replacement levels. Taking |replacement_level| and adding it boosts scarce-position players proportionally. A catcher and first baseman with identical raw WERTH will differ in position-adjusted WERTH because the replacement-level catcher is much worse than the replacement-level 1B.

### 2.3 Replacement Level Calculation

Replacement level is **position-specific** and **league-size-dependent**.

**Formula** (`Filter-H!AT4` for Catcher):
```excel
=IFERROR(
  LARGE(IF($AJ$2:$AJ$584=AP4, $AK$2:$AK$584), MAX(AS4, AR4)+1),
  SMALL(IF($AJ$2:$AJ$584=AP4, $AK$2:$AK$584), 1)
)
```

**Translation**: Find the WERTH of the **(N+1)th best player** at that position, where N = max(already_drafted_keepers, total_roster_slots). This is the classic "first player you can't start" definition.

**Special cases:**
- **DH**: `AT15 = MAX(AT4:AT14) + STDEV(AT4:AT14)` — DH replacement is set to 1 stdev above the worst position's replacement, since DH-only players compete against all hitters
- **Flex positions** (CI/MI/IF): Uses `Pre!$DX` to find the best non-starter across eligible positions
- **League size scaling**: `AR4 = AQ4 × AR2` — more teams means deeper starter pools, lower replacement level, greater spread between positions

### 2.4 Projection Sources and Aggregation

| # | Source | Notes |
|---|--------|-------|
| 1 | THE BAT | |
| 2 | Steamer | FanGraphs standard |
| 3 | ZiPS | Dan Szymborski's system |
| 4 | FanGraphs Depth Charts | Consensus of Steamer + ZiPS + manual playing time |
| 5 | Clay Davenport | |
| 6 | Steamer-600 | Full-season rate (600 PA / 200 IP) |
| 7 | OOPSY | |
| 8 | Marcel | Tom Tango's baseline system |
| 9 | Avg of Base | Simple average of sources 1-8 |
| 10 | Mr. Cheatsheet Blend | Author's proprietary weights |
| 11 | Custom Combo | User-defined weighted blend |
| 12 | Import Your Own | Paste-in slot |

The custom combo formula allows any weighting across sources 1-10 (must sum to 100%).

### 2.5 League Customization Capabilities

| Feature | Range | Location |
|---------|-------|----------|
| Teams | 6-24 | Settings!K4 |
| Draft type | Snake/Linear | Settings!K5 |
| Hitting categories | Up to 12 from 23 options | Settings!C4:D15 |
| Pitching categories | Up to 12 from 27 options | Settings!C18:D29 |
| Category weighting | Full (1.0) or Half (0.5) | Settings!D column |
| Roster positions | C, 1B, 2B, 3B, SS, OF(1-9), DH, CI, MI, IF, LF, CF, RF, SP, RP, P, Bench | Settings!G4:G22 |
| League type | Mixed, AL-Only, NL-Only, Specific Teams | Settings!M4 |
| Multi-position eligibility | Games played or started threshold | Settings!S10:S13 |
| Ohtani handling | Hitter-only, pitcher-only, both, or split | Settings!R15:R17 |

### 2.6 Non-Standard Category Support

**All of our league's categories are natively supported:**

| Our Category | Mr. Cheatsheet Name | Guts-1 Row | Type |
|-------------|---------------------|-----------|------|
| R | R | Row 1 | Counting |
| HR | HR | Row 3 | Counting |
| TB | TB | Row 10 | Counting |
| RBI | RBI | Row 4 | Counting |
| SBN (Net SB) | SB-CS | Row 9 | Counting |
| OBP | OBP | Row 14 | Rate (M=2) |
| K (strikeouts) | K | Row 3 (pitching) | Counting |
| QS | QS | Row 6 (pitching) | Counting |
| ERA | ERA | Row 1 (pitching) | Rate (M=4, IP-weighted) |
| WHIP | WHIP | Row 2 (pitching) | Rate (M=4, IP-weighted) |
| K/BB | K/BB | Row 10 (pitching) | Rate (M=3) |
| SVHD (SV+HLD) | SV+HLD | Row 8 (pitching) | Counting |

### 2.7 Draft-Day Interface

1. **Player list** in "Your Roto Draft" sheet, sorted by ADP or WERTH (toggle at P4)
2. **Click-to-draft**: VBA `Worksheet_SelectionChange` — clicking a player name populates cell B5 ("Player To Pick")
3. **Confirm pick**: Button triggers VBA macro writing player to Draft Log at current pick number
4. **Draft Log** tracks pick #, round, player, team — supports snake/linear draft order and keepers
5. **Current pick** found by: `=INDEX('Draft Log'!A3:A870, MATCH("Y", 'Draft Log'!F3:F870, 0))`
6. **Filtering**: Show/hide drafted players (P6 toggle), filter by position (P5 dropdown)
7. **Notes**: Clicking column D shows a MsgBox with custom player notes
8. **In-draft standings projection**: Projected Standings sheet updates as picks are made

**Speed assessment**: All calculations are formula-based and recalculate instantly. The VBA is simple event handling. Should easily work within a 60-second pick window in Excel. A Python reimplementation would be even faster.

### 2.8 VBA Macros (UI Only)

All VBA is UI/workflow code — no valuation logic:

- **Module1**: `Process_Picks()` (lock Keepers, stamp draft log), `UnProcess_Picks()`, `Search()`, `Search_And_Place()`, `Fix_The_Sheet()`
- **Sheet2** (Your Roto Draft): `Worksheet_SelectionChange` — click-to-draft and notes popup
- **Sheet23/24** (Save/Load): Serializes settings, keepers, notes, draft picks to/from a paste-able format

All sheets are protected with password `YQK_9_s$@+U*8@P3bQE+=GKqE#?^Qmyx`.

---

## 3. Valuation Methodology Comparison

### 3.1 SGP (Standings Gain Points)

**How it works:**
1. Calculate SGP denominators using `SLOPE()` on historical league standings data — how many units of each stat = 1 standings point
2. `SGP_per_category = projected_stat / denominator` (counting stats)
3. For rate stats: compute marginal team impact, then divide by denominator
4. `Total_SGP = SUM(all_category_SGPs)`
5. Subtract position-specific replacement level
6. Convert to dollars: `dollars = (SGP_above_replacement × $/SGP) + $1`

**Strengths**: Won the FanGraphs valuation test decisively ("the Mike Trout of valuation systems"). Empirically calibrated to actual standings movement.

**Weaknesses**: Requires historical standings data *from your exact league format*. Designed for roto, not H2H categories. Harder to calculate for non-standard categories.

### 3.2 Z-Score (what WERTH uses)

**How it works:**
1. Define the starter pool based on league size and roster
2. Calculate mean and stdev of each category across starters
3. `z_score = (player_stat - mean) / stdev` per category
4. For rate stats: convert to counting equivalents first, then z-score
5. `Total_value = SUM(all_category_z_scores)`
6. Apply position-specific replacement level adjustment

**Strengths**: Only requires projections, no historical data. Better suited for H2H. Easier to adapt to non-standard categories. Self-contained.

**Weaknesses**: Ranked 3rd-8th in FanGraphs test (depending on implementation). May overvalue elite ratios relative to SGP.

### 3.3 Which Is Best for Our League?

**Z-scores (WERTH approach) is the clear winner for our use case:**

1. **H2H categories, not roto** — SGP was designed for and calibrated against roto standings. We don't have roto standings to derive denominators from.
2. **Non-standard categories** — TB, SBN, K/BB, SVHD don't have widely available SGP denominators. Z-scores only need projections.
3. **8-team league** — Limited historical data for this specific format. Z-scores self-calibrate from projections.
4. **Mr. Cheatsheet already implements it** — Proven, debugged, with smart handling of rate stats.

**One enhancement to consider**: For H2H specifically, player consistency (low weekly variance) has additional value beyond what z-scores capture. A player who reliably produces 2 HR/week is worth more in H2H than one who hits 8 in one week and 0 for three weeks, even if their season totals are identical. This could be layered on top of the WERTH approach.

---

## 4. What We Can Borrow from Mr. Cheatsheet

### 4.1 Directly Reusable Components

| Component | What to Borrow | Adaptation Needed |
|-----------|---------------|-------------------|
| **Rate stat conversion formulas** | AVGc/OBPc/ERAc/WHIPc/K-BBc methodology | None — these are mathematically sound and handle all our rate categories |
| **Replacement level calculation** | Position-specific (N+1)th-best approach | Recalculate for 8 teams and our roster settings |
| **Category mapping system** | Guts-1 architecture mapping category names → column indices → conversion types | Simplify to just our 12 categories |
| **Position-adjusted WERTH** | |replacement_level| + raw_WERTH + multi-pos bonus | Keep the concept, tune the bonus value |
| **Projection blending** | Weighted average across multiple projection systems | Use Steamer + ATC as our two sources |

### 4.2 Clever Techniques Worth Carrying Forward

1. **Rate stat "counting conversion"** — The marginal-team-impact approach is the gold standard. Don't reinvent this.
2. **Position-based starter pool** — Defining the pool by `slots × teams` per position (not just "top N players overall") correctly captures positional scarcity.
3. **Negating stdev for "lower is better" stats** — Simple but essential for keeping z-score direction consistent.
4. **DH replacement level formula** — `MAX(position_replacements) + STDEV(position_replacements)` elegantly handles utility/DH spots.
5. **Multi-position eligibility bonus** — The +0.5 bonus for multi-eligible players is a reasonable rule of thumb for the roster flexibility value.
6. **Category weighting** — Full/Half weights allow expressing that some categories matter more. We could extend this with more granular weights.

### 4.3 What to Simplify

- Mr. Cheatsheet supports 23 hitting + 27 pitching categories, 10 projection sources, 6-24 teams, multiple ADP sources, and many exotic options. We only need our 12 specific categories, 2 projection sources, and 8-team configuration. A purpose-built tool can be much simpler.

---

## 5. Gaps for Our Use Case

### 5.1 H2H Categories vs Roto

**Mr. Cheatsheet is designed for roto leagues.** The WERTH formula measures season-long cumulative value — exactly what matters in roto. In H2H categories, what matters is **winning individual category matchups each week**. This creates several gaps:

1. **No consistency/variance modeling** — A player who puts up 30 HR in bursts is worth the same WERTH as one who hits 30 HR evenly across the season. In H2H, the consistent player is more valuable because you need to win categories *each week*.

2. **No category balance optimization** — In roto, being elite in one category and terrible in another averages out. In H2H, you want to be competitive in *all* categories (or strategically punt specific ones). Mr. Cheatsheet doesn't model this.

3. **No streaming/waiver value modeling** — In an 8-team H2H league, the waiver wire is deep. Players who provide streaming flexibility (short-term value from pitchers making spot starts, etc.) have additional worth not captured by season-long projections.

4. **No weekly projection modeling** — Season projections divided by ~26 weeks is a rough approximation of weekly output, but doesn't account for scheduling, rest days, or matchup strength.

### 5.2 8-Team Specific Gaps

1. **Compressed value scale** — In 8 teams, the difference between the #1 player and the #80 player is smaller than in 12+ teams. Mr. Cheatsheet's WERTH scale may need recalibration to be meaningfully differentiated at this depth.

2. **Reduced positional scarcity** — With only 8 of each position drafted, even "scarce" positions have strong replacement options. The position adjustment formula may overvalue positional scarcity in this context.

3. **In-draft roster construction** — Mr. Cheatsheet tracks your roster but doesn't optimize for category balance. In H2H with 8 teams, you want a tool that says "you're weak in SBN and K/BB — prioritize players strong in those categories."

### 5.3 Keeper League Gaps

Mr. Cheatsheet has a Keepers sheet for entering pre-draft keeper selections. However:

1. **No keeper value-over-cost analysis** — For keeper leagues with round-based costs, you need to assess whether keeping a player is worth the draft pick you sacrifice.
2. **No draft capital modeling** — After keepers are set, available draft capital changes. The tool doesn't model "given these keepers are off the board, what's the optimal draft strategy?"

### 5.4 Missing Features for Draft Day

1. **No real-time category gap analysis** — "You need HR more than SB right now" type guidance
2. **No BPA-vs-need recommendation** — Balancing best player available against roster needs
3. **No ADP-vs-WERTH value alerts** — "This player's ADP is 85 but their WERTH ranks them 40 — steal alert"
4. **No opponent draft tracking** — Knowing what your opponents have drafted helps in H2H

---

## 6. Recommended Approach

### 6.1 Build-vs-Borrow Decision Matrix

| Component | Decision | Rationale |
|-----------|----------|-----------|
| **Z-score valuation engine** | **Borrow** from Mr. Cheatsheet | Proven, mathematically sound. Reimplement in Python for speed and flexibility. |
| **Rate stat conversion** | **Borrow** directly | The counting-equivalent conversion (AVGc, ERAc, etc.) is the correct approach. Copy the formulas. |
| **Replacement level** | **Borrow** with modification | Use the (N+1)th-best-at-position approach but calibrate for 8 teams and our roster. |
| **Position adjustment** | **Borrow** with modification | Use |replacement_level| + WERTH but may want to dampen the effect for 8-team depth. |
| **Projection data pipeline** | **Build new** | Python script to load FanGraphs CSVs, calculate TB/SBN/SVHD, merge via SFBB ID map. |
| **H2H category balance advisor** | **Build new** | Track your team's category strengths/weaknesses as you draft. Mr. Cheatsheet has nothing like this. |
| **Draft-day UI** | **Build new** | Python/terminal-based for speed. Mr. Cheatsheet's Excel VBA is adequate but not extensible. |
| **Keeper value analysis** | **Build new** | Round-cost vs. player-value comparison. Simple to implement once WERTH values exist. |
| **ADP-vs-value alerts** | **Build new** | Compare ADP rank to WERTH rank. Flag players with ADP significantly worse than their value. |
| **Opponent tracking** | **Build new** | Track all draft picks, project opponent category strengths, identify exploitable weaknesses. |
| **Weekly consistency modeling** | **Consider building** | Use Steamer quantile data (q10-q90) to estimate weekly variance. Layer as a tiebreaker on top of WERTH. |

### 6.2 Implementation Architecture

```
┌─────────────────────────────────────────────────┐
│                  DATA LAYER                      │
│  FanGraphs CSVs → Pandas DataFrames              │
│  Steamer + ATC projections                       │
│  SFBB ID Map for ESPN cross-reference            │
│  Calculate: TB, SBN, SVHD from components        │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              VALUATION ENGINE                    │
│  (Port Mr. Cheatsheet's WERTH to Python)         │
│                                                  │
│  1. Define starter pool (8 teams × roster)       │
│  2. Convert rate stats to counting equivalents   │
│  3. Calculate mean/stdev per category            │
│  4. Z-score each player per category             │
│  5. Sum across categories (with weights)         │
│  6. Position-specific replacement level          │
│  7. Position-adjusted WERTH                      │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│           H2H INTELLIGENCE LAYER                 │
│  (New — not in Mr. Cheatsheet)                   │
│                                                  │
│  • Category balance tracker (your team profile)  │
│  • Category gap analysis (where you're weak)     │
│  • ADP-vs-WERTH value alerts                     │
│  • Opponent draft tracking                       │
│  • Keeper value-over-cost analysis               │
│  • Consistency bonus from Steamer quantiles      │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│              DRAFT-DAY UI                        │
│  Terminal or web-based interface                  │
│                                                  │
│  • Player rankings (sortable, filterable)        │
│  • One-click draft marking                       │
│  • Real-time recommendations                     │
│  • Category balance dashboard                    │
│  • Pick timer                                    │
└─────────────────────────────────────────────────┘
```

### 6.3 Priority Order for Building

Given the draft is Tuesday March 24 at 8 PM CDT:

1. **Data pipeline** — Load CSVs, calculate derived stats, merge projections (1-2 hours)
2. **WERTH valuation engine** — Port the z-score chain from Mr. Cheatsheet to Python (2-3 hours)
3. **Pre-draft rankings** — Generate ranked player list with position-adjusted WERTH (30 min)
4. **Keeper analysis** — Value-over-cost for keeper decisions (30 min)
5. **Draft-day tracker** — Mark picks, update available players, show recommendations (2-3 hours)
6. **Category balance advisor** — Track your team's category profile as you draft (1-2 hours)
7. **ADP value alerts** — Flag steals and reaches (30 min)
8. **Opponent tracking** — If time permits

---

## 7. Appendix: Key Formulas from Mr. Cheatsheet

### A. Rate Stat Conversion — Hitting (OBPc)

```
OBPc = ((player_OBP × player_PA) - (league_avg_OBP × player_PA))
       / (avg_starter_PA × total_starter_slots)
```
**Why**: Converts OBP into "marginal on-base events above average, scaled by team share." A .400 OBP in 200 PA contributes less to your team's OBP than a .350 OBP in 600 PA. This is the mathematically correct way to handle rate stats in fantasy.

### B. Rate Stat Conversion — Pitching (ERAc)

```
ERAc = ((player_IP / total_league_IP) × player_ERA
        + (1 - player_IP / total_league_IP) × league_ERA)
       - league_ERA
```
**Why**: Models the pitcher as replacing league-average innings on your team. A low-IP reliever's ERA impact is automatically dampened relative to a workhorse starter. This elegantly solves the SP-vs-RP valuation problem for rate stats.

### C. Per-Category Z-Score (WERTH)

```
WERTH_category = (player_stat - starter_pool_mean) / starter_pool_stdev × category_weight
```
**Why**: Standard z-score normalized to the relevant player pool (starters only, not all players). Category weight allows Full (1.0) or Half (0.5) emphasis. Uses the "converted" stat for rate categories.

### D. Position-Adjusted WERTH

```
Pos_Adj_WERTH = |replacement_level_WERTH_at_position| + Total_WERTH + multi_pos_bonus
```
**Why**: Adds back the absolute value of replacement level. Scarce positions (where replacement level is more negative) get a larger boost. Multi-position eligibility adds +0.5 for roster flexibility value.

### E. Replacement Level

```
Replacement_level = WERTH of the (N+1)th best player at position
where N = max(keepers_at_position, roster_slots × num_teams)
```
**Why**: The "first player you can't start" definition. Automatically adjusts for league size (more teams = deeper pool = lower replacement level) and keeper context (keepers remove players from the available pool).

### F. DH/Utility Replacement Level

```
DH_replacement = MAX(all_position_replacements) + STDEV(all_position_replacements)
```
**Why**: DH-only players compete against hitters at all positions. Setting their replacement 1 stdev above the worst position's replacement ensures they're valued against the overall hitter pool rather than having an artificially easy comparison.

### G. Custom Projection Blend

```
Blended_stat = Σ (weight_i / 100) × source_i_stat, for all sources where weight_i > 0
Constraint: Σ weight_i = 100
```
**Why**: Allows combining projection systems to reduce individual-system bias. Consensus projections generally outperform any single system.

### H. Starter Pool Size Per Position

```
Starters_at_position = roster_slots_at_position × num_teams
Total_hitting_starters = Σ starters across all hitting positions
Total_pitching_starters = Σ starters across all pitching positions
```
**Why**: This determines the denominator population for z-scores. Using only starters (not all MLB players) ensures the mean and stdev reflect the relevant talent pool. In an 8-team league, this creates a much more talented baseline than in a 12-team league.

---

## 8. Appendix: Projection Data Assessment

### Available FanGraphs Files

| File | Players | Key Stats |
|------|---------|-----------|
| Steamer Batters | 4,187 (266 with PA≥300) | PA, AB, R, H, 1B, 2B, 3B, HR, RBI, BB, SO, SB, CS, AVG, OBP, SLG, wOBA, WAR |
| Steamer Pitchers | 5,162 (449 with IP≥50) | W, L, GS, G, SV, HLD, BS, IP, SO, BB, ERA, WHIP, K/9, BB/9, K/BB, QS, FIP, WAR |
| ATC Batters | 627 | Same core stats + inter-system disagreement metrics |
| ATC Pitchers | 844 | Same core stats + inter-system disagreement metrics |
| SFBB ID Map | 3,825 (1,955 active) | 16+ ID systems including ESPN, FanGraphs, MLBAM |

### Steamer vs ATC Key Differences

- **Steamer**: Larger player pool, includes quantile uncertainty data (q10-q90) useful for variance modeling
- **ATC**: Curated pool (MLB-relevant only), includes inter-system disagreement metrics (InterSD, Vol, Skew) useful for identifying consensus vs. controversial projections
- **Recommended**: Use ATC as primary (consensus blend), Steamer quantiles for uncertainty/consistency modeling

### Category Coverage

All 12 league categories are fully derivable:
- **Direct columns**: R, HR, RBI, OBP, K(SO), QS, ERA, WHIP, K/BB
- **Trivial calculations**: TB (1B+2×2B+3×3B+4×HR), SBN (SB-CS), SVHD (SV+HLD)

### ID Map Join Path

```
FanGraphs projections (xMLBAMID) → SFBB ID Map (MLBID) → ESPN ID (ESPNID)
```
74% of active players have ESPN IDs. Coverage for fantasy-relevant players in an 8-team league should be ~95%+.

---

## 9. Correlated Uncertainty Model

### 9.1 Why Scalar Sigma Falls Short

The original `risk_adjusted_werth.py` used Steamer wOBA/ERA quantiles to estimate a single σ per player, then applied `E[max(X, w)]` with a normal assumption. This has three problems: (1) it treats all categories as independent — a "bad season" for HR doesn't correlate with RBI, which is wrong; (2) it relies on scipy (unavailable in our environment); (3) it uses only one projection system's quantiles.

### 9.2 Cross-System Disagreement as Variance Proxy

The new model (`model/correlated_uncertainty.py`) uses 8 FanGraphs projection systems' disagreement as a proxy for outcome uncertainty. For each player-category pair with ≥3 systems reporting, we compute the standard deviation of projections across systems. This captures both "the projection community disagrees about this player" and "this player has a wide range of plausible outcomes."

Cross-system disagreement underestimates true variance by approximately 50% (projection systems share methodology and data). We correct this using ATC's published InterSD and IntraSD metrics, which measure between-system and within-system variance respectively. The inflation factor is `sqrt(1 + IntraSD²/InterSD²)`.

### 9.3 Correlation Structure

Empirical correlations from cross-system residuals (2666 batters, 4053 pitchers):

**Batters**: HR/TB/RBI form a tightly correlated cluster (r≈0.96). SBN is moderately correlated with counting stats (r≈0.7). OBP is largely independent (r≈0.3 with everything). PA drives all counting stats (r>0.9 with R/TB/RBI).

**Pitchers**: IP/K are tightly correlated (r=0.97). ERA/WHIP are moderately correlated (r=0.48). KBB is inversely correlated with ERA (r=-0.4). SVHD is independent of everything (r<0.05) — this makes sense since saves/holds depend on team role, not performance quality.

### 9.4 Simulation Engine

For each player: (1) build a variance vector from cross-system disagreement + inflation; (2) use Cholesky decomposition on the category correlation matrix; (3) draw 2000 correlated multivariate normal samples; (4) convert each sample through the z-score/WERTH chain; (5) apply truncated expectation against waiver floor. The resulting distribution gives risk_adj_werth_mc (mean of max(sim, waiver_floor)), werth_std_sim (σ of WERTH outcomes), and percentile/skew statistics.

Key design: simulations are **recentered** on the ATC-based pos_adj_werth. The MC engine provides the distribution *shape* (spread, skew, tails), but the *center* comes from the ATC point estimate. This prevents the multi-system consensus from overriding ATC's curated projections.

### 9.5 Waiver Floor Differentiation

Position players use the 4th-best free agent at their position as waiver floor. Pitchers (SP/RP) use the 16th-best, reflecting much deeper pitching waiver pools in practice. This matters because a higher waiver floor increases the option value of dropping a busted player — pitchers are more replaceable via waivers, so the "insurance" from the waiver wire is worth more for pitchers.

### 9.6 Injury Model

`model/injury_model.py` estimates expected games missed using:
- **PA/IP gap**: difference between full-season benchmark (680 PA for position players, 200 IP for SP, 65 IP for RP) and realistic projection. Healthy everyday players project 620-660 PA, creating a natural 4-12 game gap.
- **Irreducible floor**: 8 games for position players, 10 for pitchers — even fully healthy players average ~8 games missed per season.
- **Cross-system disagreement bonus**: high PA/IP disagreement across systems adds up to 10 additional expected missed games.

`model/current_injuries.py` overlays real-time injury data (as of draft day) with hand-curated games-missed estimates. The `merge_injury_data()` function takes max(projection-based, current) to avoid double-counting.

### 9.7 Integration Points for Claude Code

The pipeline runs: `run_valuation()` → `run_correlated_uncertainty()` → `build_combined_rankings()` → `merge_injury_data()` → `export_csv()` + `export_draft_tool_json()`.

**What's in the JSON** (per player): All existing fields plus `games_missed` (float, expected games missed), `injury_note` (string, e.g. "IL (30g)"), `werth_q10`/`werth_q90` (10th/90th percentile WERTH), `werth_skew` (distribution asymmetry).

**What still needs building in the draft tool HTML**:
1. Injury badge in the player row (e.g., red "IL 30g" chip next to player name)
2. Tooltip or column for games_missed_total
3. Optional: color-code werth_sigma column using q10/q90 range
4. Optional: integrate games_missed into draft value (PA-discount the WERTH by expected missed fraction)
