"""
Build the single-file HTML draft tool with all data inlined.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "model" / "output"
DRAFT_TOOL = ROOT / "draft_tool"
DRAFT_TOOL.mkdir(parents=True, exist_ok=True)


def build_html():
    # Load the data blob
    with open(OUTPUT / "draft_data.json") as f:
        data_blob = json.load(f)

    data_json = json.dumps(data_blob)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Brohei Brotanis Draft Tool 2026</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif; background: #0a0e17; color: #e0e6ed; font-size: 13px; }}
.app {{ display: grid; grid-template-columns: 1fr 380px; grid-template-rows: auto 1fr; height: 100vh; gap: 0; }}
.header {{ grid-column: 1 / -1; background: #111827; padding: 8px 16px; display: flex; align-items: center; gap: 16px; border-bottom: 2px solid #1e40af; }}
.header h1 {{ font-size: 18px; color: #60a5fa; white-space: nowrap; }}
.header .pick-info {{ font-size: 14px; color: #9ca3af; }}
.header .pick-info strong {{ color: #fbbf24; }}
.controls {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
.controls input, .controls select {{ background: #1f2937; border: 1px solid #374151; color: #e0e6ed; padding: 4px 8px; border-radius: 4px; font-size: 13px; }}
.controls input[type="text"] {{ width: 200px; }}
.controls select {{ min-width: 80px; }}
.controls button {{ background: #1e40af; color: white; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }}
.controls button:hover {{ background: #2563eb; }}
.controls button.danger {{ background: #991b1b; }}
.controls button.danger:hover {{ background: #dc2626; }}
.main-panel {{ overflow: hidden; display: flex; flex-direction: column; }}
.table-container {{ flex: 1; overflow-y: auto; overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
thead {{ position: sticky; top: 0; z-index: 10; }}
th {{ background: #1f2937; padding: 6px 8px; text-align: left; cursor: pointer; white-space: nowrap; border-bottom: 2px solid #374151; user-select: none; }}
th:hover {{ background: #374151; }}
th.sorted-asc::after {{ content: ' ▲'; color: #60a5fa; }}
th.sorted-desc::after {{ content: ' ▼'; color: #60a5fa; }}
td {{ padding: 4px 8px; border-bottom: 1px solid #1f2937; white-space: nowrap; }}
tr:hover {{ background: #1f2937; }}
tr.drafted {{ opacity: 0.3; text-decoration: line-through; }}
tr.my-pick {{ background: #1e3a5f !important; }}
tr.keeper {{ background: #3f2a1e !important; }}
.z-pos {{ color: #34d399; }}
.z-neg {{ color: #f87171; }}
.z-elite {{ color: #fbbf24; font-weight: bold; }}
.value-alert {{ background: #fbbf24; color: #000; padding: 1px 4px; border-radius: 3px; font-size: 10px; font-weight: bold; }}
.injury-badge {{ background: #dc2626; color: white; padding: 1px 5px; border-radius: 3px; font-size: 10px; font-weight: bold; margin-left: 4px; white-space: nowrap; }}
.draft-btn {{ background: #059669; color: white; border: none; padding: 2px 8px; border-radius: 3px; cursor: pointer; font-size: 11px; }}
.draft-btn:hover {{ background: #10b981; }}
.sidebar {{ background: #111827; border-left: 2px solid #1e40af; display: flex; flex-direction: column; overflow-y: auto; }}
.sidebar-section {{ padding: 12px; border-bottom: 1px solid #1f2937; }}
.sidebar-section h3 {{ font-size: 14px; color: #60a5fa; margin-bottom: 8px; }}
.cat-bar {{ display: flex; align-items: center; gap: 4px; margin: 3px 0; }}
.cat-bar .cat-name {{ width: 50px; text-align: right; font-size: 11px; color: #9ca3af; }}
.cat-bar .bar-container {{ flex: 1; height: 16px; background: #1f2937; border-radius: 3px; position: relative; overflow: hidden; }}
.cat-bar .bar {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
.cat-bar .bar.strong {{ background: #059669; }}
.cat-bar .bar.weak {{ background: #dc2626; }}
.cat-bar .bar.neutral {{ background: #6b7280; }}
.cat-bar .bar-value {{ position: absolute; right: 4px; top: 0; font-size: 10px; line-height: 16px; color: white; }}
.my-roster {{ font-size: 12px; }}
.my-roster .slot {{ display: flex; justify-content: space-between; padding: 2px 0; border-bottom: 1px solid #1f2937; }}
.my-roster .slot-name {{ color: #9ca3af; width: 40px; }}
.my-roster .player-name {{ color: #e0e6ed; }}
.my-roster .empty {{ color: #4b5563; font-style: italic; }}
.keeper-input {{ margin: 4px 0; }}
.keeper-input label {{ font-size: 11px; color: #9ca3af; }}
.keeper-input select {{ width: 100%; margin-top: 2px; }}
.tab-bar {{ display: flex; gap: 0; }}
.tab {{ padding: 6px 12px; cursor: pointer; border-bottom: 2px solid transparent; color: #9ca3af; font-size: 12px; }}
.tab.active {{ border-bottom-color: #60a5fa; color: #60a5fa; }}
.tab:hover {{ color: #e0e6ed; }}
.marginal-col {{ font-weight: bold; }}
.pos-badge {{ display: inline-block; padding: 1px 5px; border-radius: 3px; font-size: 10px; font-weight: bold; }}
.pos-C {{ background: #7c3aed; }}
.pos-1B,.pos-3B,.pos-CI {{ background: #2563eb; }}
.pos-2B,.pos-SS,.pos-MI {{ background: #0891b2; }}
.pos-OF {{ background: #059669; }}
.pos-UTIL,.pos-DH {{ background: #6b7280; }}
.pos-SP {{ background: #dc2626; }}
.pos-RP {{ background: #ea580c; }}
.pos-P {{ background: #b91c1c; }}
.round-indicator {{ font-size: 10px; color: #6b7280; margin-left: 4px; }}
.modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 100; }}
.modal.active {{ display: flex; align-items: center; justify-content: center; }}
.modal-content {{ background: #1f2937; padding: 24px; border-radius: 8px; max-width: 800px; width: 95%; max-height: 80vh; overflow-y: auto; }}
.modal-content h2 {{ color: #60a5fa; margin-bottom: 16px; }}
.modal-content .close-btn {{ float: right; cursor: pointer; color: #9ca3af; font-size: 20px; }}
.draft-log {{ font-size: 11px; max-height: 200px; overflow-y: auto; }}
.draft-log .log-entry {{ padding: 2px 0; border-bottom: 1px solid #1f2937; }}
.pick-counter {{ font-size: 16px; font-weight: bold; color: #fbbf24; }}
.ac-wrapper {{ position: relative; display: inline-block; width: 220px; margin-top: 4px; }}
.ac-wrapper input {{ width: 100%; background: #1f2937; border: 1px solid #374151; color: #e0e6ed; padding: 4px 8px; border-radius: 4px; font-size: 12px; }}
.ac-wrapper input:focus {{ border-color: #60a5fa; outline: none; }}
.ac-dropdown {{ position: absolute; top: 100%; left: 0; right: 0; background: #1f2937; border: 1px solid #374151; border-top: none; border-radius: 0 0 4px 4px; max-height: 200px; overflow-y: auto; z-index: 200; display: none; }}
.ac-dropdown.show {{ display: block; }}
.ac-option {{ padding: 4px 8px; cursor: pointer; font-size: 11px; display: flex; justify-content: space-between; align-items: center; }}
.ac-option:hover, .ac-option.highlighted {{ background: #374151; }}
.ac-option .ac-name {{ color: #e0e6ed; }}
.ac-option .ac-meta {{ color: #9ca3af; font-size: 10px; }}
.keeper-chip {{ display: inline-flex; align-items: center; gap: 6px; background: #1e3a5f; border: 1px solid #2563eb; border-radius: 6px; padding: 4px 8px; margin-top: 4px; font-size: 12px; }}
.keeper-chip .chip-name {{ color: #e0e6ed; font-weight: bold; }}
.keeper-chip .chip-meta {{ color: #9ca3af; font-size: 10px; }}
.keeper-chip .chip-werth {{ color: #fbbf24; font-size: 11px; font-weight: bold; }}
.keeper-chip .chip-remove {{ color: #f87171; cursor: pointer; font-size: 14px; margin-left: 4px; }}
</style>
</head>
<body>
<div class="app">
  <div class="header">
    <h1>Brohei Brotanis Draft 2026</h1>
    <div class="pick-info">
      Pick <strong id="currentPick">-</strong> | Round <strong id="currentRound">-</strong> |
      <span id="onTheClock">-</span>
    </div>
    <div class="controls">
      <input type="text" id="searchInput" placeholder="Search players..." oninput="filterPlayers()">
      <select id="posFilter" onchange="filterPlayers()">
        <option value="ALL">All Pos</option>
        <option value="H">Hitters</option>
        <option value="P">Pitchers</option>
        <option value="C">C</option>
        <option value="1B">1B</option>
        <option value="2B">2B</option>
        <option value="SS">SS</option>
        <option value="3B">3B</option>
        <option value="OF">OF</option>
        <option value="UTIL">UTIL/DH</option>
        <option value="SP">SP</option>
        <option value="RP">RP</option>
      </select>
      <select id="sortBy" onchange="sortPlayers()">
        <option value="werth">WERTH</option>
        <option value="risk_adj_werth">Injury-Adj WERTH</option>
        <option value="draft_value">Draft Value</option>
        <option value="adp">ADP</option>
        <option value="marginal">Marginal Value</option>
        <option value="games_missed">Games Missed</option>
        <option value="z_R">z_R</option>
        <option value="z_HR">z_HR</option>
        <option value="z_TB">z_TB</option>
        <option value="z_RBI">z_RBI</option>
        <option value="z_SBN">z_SBN</option>
        <option value="z_OBP">z_OBP</option>
        <option value="z_K">z_K</option>
        <option value="z_QS">z_QS</option>
        <option value="z_ERA">z_ERA</option>
        <option value="z_WHIP">z_WHIP</option>
        <option value="z_KBB">z_KBB</option>
        <option value="z_SVHD">z_SVHD</option>
      </select>
      <label style="display:flex;align-items:center;gap:4px;font-size:12px;color:#9ca3af;">
        <input type="checkbox" id="hideDrafted" onchange="filterPlayers()" checked> Hide drafted
      </label>
      <button onclick="showKeepersModal()">Keepers</button>
      <button onclick="undoLastPick()" class="danger">Undo</button>
      <button onclick="showDraftLog()">Log</button>
    </div>
  </div>

  <div class="main-panel">
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th style="width:30px">#</th>
            <th style="width:60px">Action</th>
            <th onclick="sortByCol('name')">Player</th>
            <th onclick="sortByCol('team')">Team</th>
            <th onclick="sortByCol('position')">Pos</th>
            <th onclick="sortByCol('adp')" title="NFBC Average Draft Position">ADP</th>
            <th onclick="sortByCol('werth')">WERTH</th>
            <th onclick="sortByCol('risk_adj_werth')" title="Injury-adjusted WERTH (discounted by current injury games missed)">iW</th>
            <th onclick="sortByCol('draft_value')" title="Risk-adjusted value of drafting vs waiver wire">DV</th>
            <th onclick="sortByCol('werth_sigma')" title="Projection uncertainty (higher = more volatile)">σ</th>
            <th onclick="sortByCol('marginal')" title="Marginal value to your team">MV</th>
            <th onclick="sortByCol('games_missed')" title="Projected games missed (total)">GM</th>
            <th onclick="sortByCol('z_R')">zR</th>
            <th onclick="sortByCol('z_HR')">zHR</th>
            <th onclick="sortByCol('z_TB')">zTB</th>
            <th onclick="sortByCol('z_RBI')">zRBI</th>
            <th onclick="sortByCol('z_SBN')">zSBN</th>
            <th onclick="sortByCol('z_OBP')">zOBP</th>
            <th onclick="sortByCol('z_K')">zK</th>
            <th onclick="sortByCol('z_QS')">zQS</th>
            <th onclick="sortByCol('z_ERA')">zERA</th>
            <th onclick="sortByCol('z_WHIP')">zWHIP</th>
            <th onclick="sortByCol('z_KBB')">zKBB</th>
            <th onclick="sortByCol('z_SVHD')">zSVHD</th>
          </tr>
        </thead>
        <tbody id="playerTable"></tbody>
      </table>
    </div>
  </div>

  <div class="sidebar">
    <div class="sidebar-section">
      <h3>My Team Category Profile</h3>
      <div id="categoryBars"></div>
    </div>
    <div class="sidebar-section">
      <h3>Weakest Categories</h3>
      <div id="weakCats" style="font-size:12px;color:#f87171;"></div>
    </div>
    <div class="sidebar-section">
      <h3>My Roster (<span id="rosterCount">0</span>/25)</h3>
      <div id="myRoster" class="my-roster"></div>
    </div>
    <div class="sidebar-section">
      <h3 onclick="document.getElementById('opponentPanel').style.display=document.getElementById('opponentPanel').style.display==='none'?'block':'none'" style="cursor:pointer">Opponents ▾</h3>
      <div id="opponentPanel" style="display:none;font-size:11px;max-height:300px;overflow-y:auto;"></div>
    </div>
    <div class="sidebar-section">
      <h3>Draft Log</h3>
      <div id="sidebarLog" class="draft-log"></div>
    </div>
  </div>
</div>

<!-- Keepers Modal -->
<div class="modal" id="keepersModal">
  <div class="modal-content">
    <span class="close-btn" onclick="closeModal('keepersModal')">&times;</span>
    <h2>Enter Keepers</h2>
    <p style="color:#9ca3af;margin-bottom:12px;font-size:12px;">Enter up to 3 keepers per team. These players will be removed from the draft pool.</p>
    <div id="keeperInputs"></div>
    <div style="margin-top:12px;display:flex;gap:8px;align-items:center;">
      <button onclick="applyKeepers()" style="padding:8px 16px;">Apply Keepers</button>
      <button onclick="exportKeepersJSON()" style="padding:8px 12px;background:#374151;font-size:12px;" title="Download keepers as JSON file">Export</button>
      <button onclick="importKeepersJSON()" style="padding:8px 12px;background:#374151;font-size:12px;" title="Load keepers from JSON file">Import</button>
      <span style="font-size:11px;color:#6b7280;">Keepers auto-save to browser storage</span>
    </div>
  </div>
</div>

<!-- Draft Log Modal -->
<div class="modal" id="draftLogModal">
  <div class="modal-content">
    <span class="close-btn" onclick="closeModal('draftLogModal')">&times;</span>
    <h2>Full Draft Log</h2>
    <div id="fullDraftLog" class="draft-log" style="max-height:60vh;"></div>
  </div>
</div>

<script>
const DATA = {data_json};

// State
let players = DATA.players.map((p, i) => ({{...p, originalRank: i + 1, drafted: false, draftedBy: null, draftPick: null, isKeeper: false, marginal: 0}}));
let draftLog = [];
let currentPickNum = 1;
let myTeamId = DATA.draft_config.my_team_id;
let pickOrder = DATA.draft_config.pick_order;
let numTeams = DATA.draft_config.num_teams;
let sortCol = 'werth';
let sortDir = -1; // -1 = descending
let keeperSelections = {{}};

// --- Keeper Persistence ---
const KEEPER_STORAGE_KEY = 'brohei_draft_2026_keepers';
function saveKeepersToStorage() {{
    try {{ localStorage.setItem(KEEPER_STORAGE_KEY, JSON.stringify(keeperSelections)); }} catch(e) {{}}
}}
function loadKeepersFromStorage() {{
    try {{
        const saved = localStorage.getItem(KEEPER_STORAGE_KEY);
        if (saved) {{ keeperSelections = JSON.parse(saved); return true; }}
    }} catch(e) {{}}
    return false;
}}
function exportKeepersJSON() {{
    const blob = new Blob([JSON.stringify(keeperSelections, null, 2)], {{type: 'application/json'}});
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'keepers_2026.json';
    a.click();
}}
function importKeepersJSON() {{
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = e => {{
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = ev => {{
            try {{
                keeperSelections = JSON.parse(ev.target.result);
                saveKeepersToStorage();
                applyKeepers();
            }} catch(err) {{ alert('Invalid keepers JSON file'); }}
        }};
        reader.readAsText(file);
    }};
    input.click();
}}

const ALL_CATS = ['R','HR','TB','RBI','SBN','OBP','K','QS','ERA','WHIP','KBB','SVHD'];
const SWING_CATS = new Set(['QS', 'SVHD', 'HR']); // Categories that flip the most matchups

// Manager tendencies from 5-year historical analysis
const MANAGER_NOTES = {{
    1: 'Balanced (40% P). Early SP (R1), then SS/CI. Playoff-competitive.',
    3: '2x champ. Pitcher-heavy (48%). Dominates K/QS/WHIP/KBB. Weak: R/SBN/SVHD.',
    4: 'Hitter-focused (32% P). Early power bats (1B/3B). First P around R5.',
    5: 'Hitter-focused (36% P). Prefers CF/SS early. First P around R6.',
    6: 'Early SP investment (R2). Then speedy hitters. Balanced approach.',
    7: 'Hitter-heavy (36% P). LF/SS/3B early, first P around R5. Punt pitching.',
    9: 'Balanced (36% P). Targets CF/1B early, moderate SP (R3).',
    10: 'Your team! Hybrid: ace pitchers + elite bats.',
}};
const HITTING_CATS = ['R','HR','TB','RBI','SBN','OBP'];
const PITCHING_CATS = ['K','QS','ERA','WHIP','KBB','SVHD'];

// My roster tracking
let myRoster = [];
let myTeamZScores = {{}};
ALL_CATS.forEach(c => myTeamZScores[c] = 0);

// Opponent tracking: z-scores and roster counts per team
let teamProfiles = {{}};
DATA.draft_config.teams.forEach(t => {{
    teamProfiles[t.team_id] = {{
        zScores: {{}},
        hitters: 0, pitchers: 0,
        players: [],
    }};
    ALL_CATS.forEach(c => teamProfiles[t.team_id].zScores[c] = 0);
}});

// Draft order helpers
function getTeamForPick(pickNum) {{
    const round = Math.ceil(pickNum / numTeams);
    const posInRound = ((pickNum - 1) % numTeams);
    // Snake: odd rounds go forward, even rounds go backward
    const idx = (round % 2 === 1) ? posInRound : (numTeams - 1 - posInRound);
    return pickOrder[idx];
}}

function getMyPicks() {{
    const picks = [];
    for (let p = 1; p <= 25 * numTeams; p++) {{
        if (getTeamForPick(p) === myTeamId) picks.push(p);
    }}
    return picks;
}}

function isMyPick(pickNum) {{
    return getTeamForPick(pickNum) === myTeamId;
}}

// Z-score formatting
function fmtZ(val) {{
    if (val === 0 || val === undefined || val === null) return '<span style="color:#4b5563">-</span>';
    const cls = val >= 2 ? 'z-elite' : val > 0 ? 'z-pos' : 'z-neg';
    return `<span class="${{cls}}">${{val.toFixed(2)}}</span>`;
}}

// ADP value alert: compare WERTH rank vs ADP
function adpBadge(p) {{
    if (!p.adp || p.adp > 250 || p.drafted) return '';
    const werthRank = p.originalRank;
    const adpRound = Math.ceil(p.adp / numTeams);
    const werthRound = Math.ceil(werthRank / numTeams);
    const roundDiff = adpRound - werthRound; // positive = WERTH says better than ADP
    if (roundDiff >= 3) return ' <span class="value-alert" title="WERTH ranks ' + roundDiff + ' rounds better than ADP — steal">STEAL</span>';
    if (roundDiff <= -3) return ' <span style="background:#991b1b;color:#fca5a5;padding:1px 4px;border-radius:3px;font-size:10px;font-weight:bold" title="WERTH ranks ' + (-roundDiff) + ' rounds worse than ADP — reach">REACH</span>';
    return '';
}}

// Marginal value: how much does this player help my weakest categories?
function computeMarginalValues() {{
    // Find my weakest categories (lowest z-score sums)
    const catScores = ALL_CATS.map(c => ({{cat: c, score: myTeamZScores[c]}}));
    catScores.sort((a, b) => a.score - b.score);
    const weakCats = catScores.slice(0, 4).map(c => c.cat);
    const weakSet = new Set(weakCats);

    players.forEach(p => {{
        if (p.drafted) {{ p.marginal = -999; return; }}
        let mv = 0;
        weakCats.forEach(cat => {{
            const zCol = 'z_' + cat;
            const zVal = p[zCol] || 0;
            if (zVal > 0) mv += zVal * 1.5; // boost for helping weak cats
        }});
        // Also add some base WERTH (use risk-adjusted to incorporate injury discount)
        mv += (p.risk_adj_werth || p.werth || 0) * 0.3;
        p.marginal = mv;
    }});

    // Update weak cats display
    const weakDiv = document.getElementById('weakCats');
    weakDiv.innerHTML = catScores.slice(0, 4).map(c =>
        `<span style="margin-right:8px;">${{c.cat}}: ${{c.score.toFixed(2)}}</span>`
    ).join('');
}}

// Render player table
function renderTable() {{
    const tbody = document.getElementById('playerTable');
    const hideDrafted = document.getElementById('hideDrafted').checked;
    const search = document.getElementById('searchInput').value.toLowerCase();
    const posFilter = document.getElementById('posFilter').value;

    let filtered = players.filter(p => {{
        if (hideDrafted && p.drafted) return false;
        if (search && !p.name.toLowerCase().includes(search) && !p.team.toLowerCase().includes(search)) return false;
        if (posFilter === 'ALL') return true;
        if (posFilter === 'H') return p.type === 'H';
        if (posFilter === 'P') return p.type === 'P';
        return p.position === posFilter || (posFilter === 'UTIL' && (p.position === 'UTIL' || p.position === 'DH'));
    }});

    // Sort
    filtered.sort((a, b) => {{
        let aVal = a[sortCol];
        let bVal = b[sortCol];
        // Null/undefined values sort to end regardless of direction
        if (aVal == null && bVal == null) return 0;
        if (aVal == null) return 1;
        if (bVal == null) return -1;
        aVal = aVal || 0;
        bVal = bVal || 0;
        if (typeof aVal === 'string') return sortDir * aVal.localeCompare(bVal);
        return sortDir * (aVal - bVal);
    }});

    // Limit to top 200 for performance
    filtered = filtered.slice(0, 200);

    let html = '';
    filtered.forEach((p, i) => {{
        const rowClass = [
            p.drafted ? 'drafted' : '',
            p.draftedBy === myTeamId ? 'my-pick' : '',
            p.isKeeper ? 'keeper' : '',
        ].filter(Boolean).join(' ');

        const posClass = 'pos-' + p.position;
        const actionHtml = p.drafted
            ? `<span style="font-size:10px;color:#6b7280;">${{p.draftedBy === myTeamId ? 'MINE' : 'Taken'}}</span>`
            : `<button class="draft-btn" onclick="draftPlayer(${{players.indexOf(p)}})">Draft</button>`;

        html += `<tr class="${{rowClass}}" data-idx="${{players.indexOf(p)}}">
            <td>${{p.originalRank}}</td>
            <td>${{actionHtml}}</td>
            <td>${{p.name}}${{p.is_two_way ? ' <span style="color:#fbbf24;font-size:10px;">2W</span>' : ''}}${{p.injury_note ? ' <span class="injury-badge" title="' + p.injury_note + '">' + p.injury_note + '</span>' : ''}}</td>
            <td>${{p.team}}</td>
            <td><span class="pos-badge ${{posClass}}">${{p.position}}</span></td>
            <td style="font-size:11px;color:#9ca3af">${{p.adp ? p.adp.toFixed(0) : '-'}}${{adpBadge(p)}}</td>
            <td style="font-weight:bold">${{p.werth.toFixed(1)}}</td>
            <td style="color:${{p.risk_adj_werth < p.werth - 0.1 ? '#f87171' : '#9ca3af'}};font-weight:${{p.risk_adj_werth < p.werth - 0.1 ? 'bold' : 'normal'}}">${{(p.risk_adj_werth || 0).toFixed(1)}}</td>
            <td style="color:${{p.draft_value > 10 ? '#34d399' : p.draft_value > 5 ? '#fbbf24' : p.draft_value > 0 ? '#9ca3af' : '#f87171'}};font-weight:${{p.draft_value > 10 ? 'bold' : 'normal'}}">${{(p.draft_value || 0).toFixed(1)}}</td>
            <td style="color:${{p.werth_sigma > 5 ? '#fbbf24' : '#6b7280'}};font-size:11px">${{(p.werth_sigma || 0).toFixed(1)}}</td>
            <td class="marginal-col" style="color:${{p.marginal > 3 ? '#34d399' : p.marginal > 1 ? '#fbbf24' : '#9ca3af'}}">${{p.marginal > -900 ? p.marginal.toFixed(1) : '-'}}</td>
            <td style="color:${{p.games_missed >= 30 ? '#f87171' : p.games_missed >= 15 ? '#fbbf24' : '#6b7280'}};font-size:11px">${{p.games_missed > 0 ? Math.round(p.games_missed) : '-'}}</td>
            <td>${{fmtZ(p.z_R)}}</td>
            <td>${{fmtZ(p.z_HR)}}</td>
            <td>${{fmtZ(p.z_TB)}}</td>
            <td>${{fmtZ(p.z_RBI)}}</td>
            <td>${{fmtZ(p.z_SBN)}}</td>
            <td>${{fmtZ(p.z_OBP)}}</td>
            <td>${{fmtZ(p.z_K)}}</td>
            <td>${{fmtZ(p.z_QS)}}</td>
            <td>${{fmtZ(p.z_ERA)}}</td>
            <td>${{fmtZ(p.z_WHIP)}}</td>
            <td>${{fmtZ(p.z_KBB)}}</td>
            <td>${{fmtZ(p.z_SVHD)}}</td>
        </tr>`;
    }});

    tbody.innerHTML = html;
}}

// Draft a player
function draftPlayer(idx, teamOverride) {{
    const p = players[idx];
    if (p.drafted) return;

    const teamId = teamOverride || getTeamForPick(currentPickNum);
    p.drafted = true;
    p.draftedBy = teamId;
    p.draftPick = currentPickNum;

    const teamName = DATA.draft_config.teams.find(t => t.team_id === teamId)?.team_name || `Team ${{teamId}}`;

    draftLog.push({{
        pick: currentPickNum,
        round: Math.ceil(currentPickNum / numTeams),
        player: p.name,
        position: p.position,
        teamId: teamId,
        teamName: teamName,
        werth: p.werth,
    }});

    // Update team profile
    if (teamProfiles[teamId]) {{
        const tp = teamProfiles[teamId];
        ALL_CATS.forEach(cat => {{ tp.zScores[cat] += (p['z_' + cat] || 0); }});
        if (p.type === 'H') tp.hitters++; else tp.pitchers++;
        tp.players.push(p);
    }}

    // If it's my pick, add to roster and update z-scores
    if (teamId === myTeamId) {{
        myRoster.push(p);
        ALL_CATS.forEach(cat => {{
            myTeamZScores[cat] += (p['z_' + cat] || 0);
        }});
    }}

    currentPickNum++;
    updateUI();
}}

// Undo last pick
function undoLastPick() {{
    if (draftLog.length === 0) return;
    const last = draftLog.pop();
    currentPickNum--;

    const p = players.find(pl => pl.name === last.player && pl.draftPick === last.pick);
    if (p) {{
        p.drafted = false;
        p.draftedBy = null;
        p.draftPick = null;

        // Reverse team profile
        if (teamProfiles[last.teamId]) {{
            const tp = teamProfiles[last.teamId];
            ALL_CATS.forEach(cat => {{ tp.zScores[cat] -= (p['z_' + cat] || 0); }});
            if (p.type === 'H') tp.hitters--; else tp.pitchers--;
            tp.players = tp.players.filter(r => r !== p);
        }}

        if (last.teamId === myTeamId) {{
            myRoster = myRoster.filter(r => r !== p);
            ALL_CATS.forEach(cat => {{
                myTeamZScores[cat] -= (p['z_' + cat] || 0);
            }});
        }}
    }}
    updateUI();
}}

// Update all UI elements
function updateUI() {{
    const teamId = getTeamForPick(currentPickNum);
    const teamName = DATA.draft_config.teams.find(t => t.team_id === teamId)?.team_name || `Team ${{teamId}}`;
    const round = Math.ceil(currentPickNum / numTeams);

    document.getElementById('currentPick').textContent = currentPickNum;
    document.getElementById('currentRound').textContent = round;
    document.getElementById('onTheClock').textContent = isMyPick(currentPickNum)
        ? '🎯 YOUR PICK!'
        : `On clock: ${{teamName}}`;
    document.getElementById('onTheClock').style.color = isMyPick(currentPickNum) ? '#fbbf24' : '#9ca3af';

    computeMarginalValues();
    renderTable();
    renderCategoryBars();
    renderMyRoster();
    renderOpponents();
    renderSidebarLog();
}}

// Render category bars
function renderCategoryBars() {{
    const container = document.getElementById('categoryBars');
    // Normalize: show z-scores relative to a "competitive" baseline
    // In an 8-team league, z=0 per category is average for a starter
    // After drafting ~13 hitters and ~9 pitchers, we want each cat > 0
    const maxZ = 10;

    let html = '';
    ALL_CATS.forEach(cat => {{
        const val = myTeamZScores[cat];
        const pct = Math.min(100, Math.max(0, ((val + maxZ) / (2 * maxZ)) * 100));
        const barClass = val > 1 ? 'strong' : val < -1 ? 'weak' : 'neutral';
        const isSwing = SWING_CATS.has(cat);
        const swingBadge = isSwing ? '<span style="color:#fbbf24;font-size:9px;margin-left:2px" title="Swing category - flips most matchups">★</span>' : '';
        const borderStyle = isSwing ? 'border:1px solid #fbbf2466;border-radius:4px;padding:1px;' : '';
        html += `<div class="cat-bar" style="${{borderStyle}}">
            <span class="cat-name">${{cat}}${{swingBadge}}</span>
            <div class="bar-container">
                <div class="bar ${{barClass}}" style="width:${{pct}}%"></div>
                <span class="bar-value">${{val.toFixed(1)}}</span>
            </div>
        </div>`;
    }});
    container.innerHTML = html;
}}

// Render my roster
function renderMyRoster() {{
    const container = document.getElementById('myRoster');
    document.getElementById('rosterCount').textContent = myRoster.length;

    if (myRoster.length === 0) {{
        container.innerHTML = '<div class="empty">No players drafted yet</div>';
        return;
    }}

    let html = '';
    myRoster.forEach(p => {{
        html += `<div class="slot">
            <span class="slot-name">${{p.position}}</span>
            <span class="player-name">${{p.name}}</span>
        </div>`;
    }});
    container.innerHTML = html;
}}

// Render sidebar draft log
function renderSidebarLog() {{
    const container = document.getElementById('sidebarLog');
    const recent = draftLog.slice(-15).reverse();
    let html = '';
    recent.forEach(entry => {{
        const isMe = entry.teamId === myTeamId;
        html += `<div class="log-entry" style="color:${{isMe ? '#60a5fa' : '#9ca3af'}}">
            R${{entry.round}}.${{entry.pick}}: ${{entry.player}} (${{entry.position}}) → ${{entry.teamName}}
        </div>`;
    }});
    container.innerHTML = html || '<div class="empty">No picks yet</div>';
}}

// Render opponent profiles
function renderOpponents() {{
    const panel = document.getElementById('opponentPanel');
    if (!panel || panel.style.display === 'none') return;

    let html = '';
    DATA.draft_config.teams.forEach(team => {{
        if (team.team_id === myTeamId) return;
        const tp = teamProfiles[team.team_id];

        // Always show teams with notes, even if no picks yet
        const note = MANAGER_NOTES[team.team_id] || '';
        if (!tp || (tp.players.length === 0 && !note)) return;

        // Find weakest 3 categories
        const catArr = ALL_CATS.map(c => ({{cat: c, z: tp.zScores[c]}}));
        catArr.sort((a, b) => a.z - b.z);
        const weakCats = catArr.slice(0, 3).map(c => c.cat);
        const strongCats = catArr.slice(-3).reverse().map(c => c.cat);

        html += `<div style="margin-bottom:8px;padding:6px;background:#0f1729;border-radius:4px;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <strong style="color:#e0e6ed;font-size:11px;">${{team.team_name}}</strong>
                <span style="color:#6b7280;font-size:10px;">${{tp.hitters}}H/${{tp.pitchers}}P</span>
            </div>
            ${{note ? `<div style="color:#9ca3af;font-size:9px;margin-top:2px;font-style:italic;">${{note}}</div>` : ''}}
            ${{tp.players.length > 0 ? `<div style="margin-top:3px;">
                <span style="color:#34d399;font-size:10px;">Strong: ${{strongCats.join(', ')}}</span>
                <span style="color:#f87171;font-size:10px;margin-left:8px;">Weak: ${{weakCats.join(', ')}}</span>
            </div>` : ''}}
            ${{tp.players.length > 0 ? `<div style="display:flex;gap:2px;margin-top:3px;flex-wrap:wrap;">` : ''}}`;
        if (tp.players.length > 0) {{
            ALL_CATS.forEach(cat => {{
                const z = tp.zScores[cat];
                const bg = z > 1 ? '#059669' : z < -1 ? '#991b1b' : '#374151';
                html += `<span style="background:${{bg}};padding:0 3px;border-radius:2px;font-size:9px;color:#e0e6ed;" title="${{cat}}: ${{z.toFixed(1)}}">${{cat[0]}}${{z > 0 ? '+' : ''}}${{z.toFixed(0)}}</span>`;
            }});
            html += `</div>`;
        }}
        html += `</div>`;
    }});

    panel.innerHTML = html || '<div style="color:#6b7280;">No opponent picks yet</div>';
}}

// Filter players
function filterPlayers() {{ renderTable(); }}

// Sort
function sortByCol(col) {{
    if (sortCol === col) {{ sortDir *= -1; }}
    else {{ sortCol = col; sortDir = -1; }}
    renderTable();
}}

function sortPlayers() {{
    sortCol = document.getElementById('sortBy').value;
    // ADP: lower is better, so sort ascending; everything else descending
    sortDir = (sortCol === 'adp') ? 1 : -1;
    renderTable();
}}

// Keepers modal with autocomplete
let activeDropdown = null;
let highlightedIdx = -1;

function showKeepersModal() {{
    const container = document.getElementById('keeperInputs');
    let html = '';
    DATA.draft_config.teams.forEach(team => {{
        html += `<div style="margin-bottom:12px;">
            <strong style="color:#e0e6ed;">${{team.team_name}} (${{team.owner}})</strong>
            <div style="display:flex;gap:6px;flex-wrap:wrap;">`;
        for (let k = 0; k < 3; k++) {{
            const key = `${{team.team_id}}_${{k}}`;
            const sel = keeperSelections[key];
            if (sel) {{
                const p = players.find(pl => pl.name === sel);
                html += `<div class="keeper-chip" id="chip-${{key}}">
                    <span class="chip-name">${{sel}}</span>
                    <span class="chip-meta">${{p ? p.team + ' ' + p.position : ''}}</span>
                    <span class="chip-werth">${{p ? p.werth.toFixed(1) : ''}}</span>
                    <span class="chip-remove" onclick="clearKeeper('${{key}}')">&times;</span>
                </div>`;
            }} else {{
                html += `<div class="ac-wrapper" id="ac-${{key}}">
                    <input type="text" data-key="${{key}}" data-team="${{team.team_id}}"
                        placeholder="Keeper ${{k+1}}..." oninput="onKeeperInput(this)" onfocus="onKeeperInput(this)"
                        onkeydown="onKeeperKeydown(event, this)">
                    <div class="ac-dropdown" id="dd-${{key}}"></div>
                </div>`;
            }}
        }}
        html += `</div></div>`;
    }});
    container.innerHTML = html;
    document.getElementById('keepersModal').classList.add('active');
}}

function onKeeperInput(input) {{
    const key = input.dataset.key;
    const dd = document.getElementById('dd-' + key);
    const query = input.value.toLowerCase().trim();
    highlightedIdx = -1;

    if (query.length < 2) {{ dd.classList.remove('show'); return; }}

    // Get already-selected keeper names
    const taken = new Set(Object.values(keeperSelections).filter(Boolean));

    // Fuzzy match: check if all query chars appear in order
    const matches = players.filter(p => {{
        if (taken.has(p.name)) return false;
        const name = p.name.toLowerCase();
        return name.includes(query) || fuzzyMatch(query, name);
    }}).slice(0, 12);

    if (matches.length === 0) {{ dd.classList.remove('show'); return; }}

    dd.innerHTML = matches.map((p, i) =>
        `<div class="ac-option" data-idx="${{i}}" onmousedown="selectKeeper('${{key}}', '${{p.name.replace(/'/g, "\\\\'")}}')">
            <span class="ac-name">${{p.name}}</span>
            <span class="ac-meta">${{p.team}} <span class="pos-badge pos-${{p.position}}" style="font-size:9px;padding:0 3px;">${{p.position}}</span> WERTH ${{p.werth.toFixed(1)}}</span>
        </div>`
    ).join('');
    dd.classList.add('show');
    activeDropdown = dd;
}}

function fuzzyMatch(query, target) {{
    let qi = 0;
    for (let ti = 0; ti < target.length && qi < query.length; ti++) {{
        if (target[ti] === query[qi]) qi++;
    }}
    return qi === query.length;
}}

function onKeeperKeydown(e, input) {{
    const key = input.dataset.key;
    const dd = document.getElementById('dd-' + key);
    const options = dd.querySelectorAll('.ac-option');
    if (!dd.classList.contains('show') || options.length === 0) return;

    if (e.key === 'ArrowDown') {{
        e.preventDefault();
        highlightedIdx = Math.min(highlightedIdx + 1, options.length - 1);
        options.forEach((o, i) => o.classList.toggle('highlighted', i === highlightedIdx));
    }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        highlightedIdx = Math.max(highlightedIdx - 1, 0);
        options.forEach((o, i) => o.classList.toggle('highlighted', i === highlightedIdx));
    }} else if (e.key === 'Enter' && highlightedIdx >= 0) {{
        e.preventDefault();
        options[highlightedIdx].dispatchEvent(new Event('mousedown'));
    }} else if (e.key === 'Escape') {{
        dd.classList.remove('show');
    }}
}}

function selectKeeper(key, playerName) {{
    keeperSelections[key] = playerName;
    saveKeepersToStorage();
    showKeepersModal(); // re-render to show chip
}}

function clearKeeper(key) {{
    delete keeperSelections[key];
    saveKeepersToStorage();
    showKeepersModal(); // re-render
}}

// Close dropdowns when clicking outside
document.addEventListener('click', e => {{
    if (!e.target.closest('.ac-wrapper')) {{
        document.querySelectorAll('.ac-dropdown.show').forEach(d => d.classList.remove('show'));
    }}
}});

function applyKeepers() {{
    // Clear existing keeper marks, my roster, and team profiles for keepers
    players.forEach(p => {{
        if (p.isKeeper) {{
            // Reverse team profile
            if (p.draftedBy && teamProfiles[p.draftedBy]) {{
                const tp = teamProfiles[p.draftedBy];
                ALL_CATS.forEach(cat => {{ tp.zScores[cat] -= (p['z_' + cat] || 0); }});
                if (p.type === 'H') tp.hitters--; else tp.pitchers--;
                tp.players = tp.players.filter(r => r !== p);
            }}
            if (p.draftedBy === myTeamId) {{
                myRoster = myRoster.filter(r => r !== p);
                ALL_CATS.forEach(cat => {{
                    myTeamZScores[cat] -= (p['z_' + cat] || 0);
                }});
            }}
            p.drafted = false;
            p.draftedBy = null;
            p.isKeeper = false;
        }}
    }});

    // Apply keepers
    Object.entries(keeperSelections).forEach(([key, name]) => {{
        if (!name || !name.trim()) return;
        const teamId = parseInt(key.split('_')[0]);
        const match = players.find(p => p.name === name && !p.drafted);
        if (match) {{
            match.drafted = true;
            match.draftedBy = teamId;
            match.isKeeper = true;

            // Update team profile
            if (teamProfiles[teamId]) {{
                const tp = teamProfiles[teamId];
                ALL_CATS.forEach(cat => {{ tp.zScores[cat] += (match['z_' + cat] || 0); }});
                if (match.type === 'H') tp.hitters++; else tp.pitchers++;
                tp.players.push(match);
            }}

            if (teamId === myTeamId) {{
                myRoster.push(match);
                ALL_CATS.forEach(cat => {{
                    myTeamZScores[cat] += (match['z_' + cat] || 0);
                }});
            }}
        }}
    }});

    closeModal('keepersModal');
    updateUI();
}}

function showDraftLog() {{
    const container = document.getElementById('fullDraftLog');
    let html = '<table style="width:100%">';
    html += '<tr><th>Pick</th><th>Rd</th><th>Player</th><th>Pos</th><th>WERTH</th><th>Team</th></tr>';
    draftLog.forEach(entry => {{
        const isMe = entry.teamId === myTeamId;
        html += `<tr style="color:${{isMe ? '#60a5fa' : '#e0e6ed'}}">
            <td>${{entry.pick}}</td><td>${{entry.round}}</td>
            <td>${{entry.player}}</td><td>${{entry.position}}</td>
            <td>${{entry.werth.toFixed(1)}}</td><td>${{entry.teamName}}</td>
        </tr>`;
    }});
    html += '</table>';
    container.innerHTML = html || 'No picks yet';
    document.getElementById('draftLogModal').classList.add('active');
}}

function closeModal(id) {{
    document.getElementById(id).classList.remove('active');
}}

// Click outside modal to close
document.querySelectorAll('.modal').forEach(modal => {{
    modal.addEventListener('click', e => {{
        if (e.target === modal) closeModal(modal.id);
    }});
}});

// Keyboard shortcut: Escape to close modals
document.addEventListener('keydown', e => {{
    if (e.key === 'Escape') {{
        document.querySelectorAll('.modal.active').forEach(m => m.classList.remove('active'));
    }}
    // Ctrl+F or / to focus search
    if ((e.ctrlKey && e.key === 'f') || (e.key === '/' && document.activeElement.tagName !== 'INPUT')) {{
        e.preventDefault();
        document.getElementById('searchInput').focus();
    }}
}});

// Initialize — restore saved keepers if any
if (loadKeepersFromStorage() && Object.keys(keeperSelections).length > 0) {{
    applyKeepers();
    console.log('Restored ' + Object.keys(keeperSelections).length + ' keeper selections from storage');
}}
computeMarginalValues();
updateUI();
</script>
</body>
</html>"""

    with open(DRAFT_TOOL / "index.html", "w") as f:
        f.write(html)

    size_kb = len(html) / 1024
    print(f"Draft tool built: {DRAFT_TOOL / 'index.html'} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    build_html()
