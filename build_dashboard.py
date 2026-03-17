from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

INPUT_CSV = "precios_historicos.csv"
OUTPUT_HTML = "index.html"

ACCENT = "#d62d20"
GREEN = "#0b1f3a"
BG = "#f8f6f0"
TEXT = "#1f1f1f"
MUTED = "#6a6a6a"
GRID = "#d9d5cc"

ORDER = ["Superior", "Regular", "Diésel"]


def prepare_data(csv_path: str | Path = INPUT_CSV) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["precio"] = pd.to_numeric(df["precio"], errors="coerce")
    df["combustible"] = df["combustible"].astype(str).str.strip()
    df = df[df["fecha"].notna() & df["precio"].notna()].copy()
    return df.sort_values(["combustible", "fecha"])


def build_payload(df: pd.DataFrame) -> dict:
    payload = {"series": {}, "summary": [], "last_update": None}
    if df.empty:
        return payload

    payload["last_update"] = df["fecha"].max().strftime("%d/%m/%Y")

    for fuel in ORDER:
        sub = df[df["combustible"] == fuel].sort_values("fecha").copy()
        if sub.empty:
            continue
        sub["prev_7"] = sub["precio"].shift(7)
        sub["prev_30"] = sub["precio"].shift(30)
        latest = sub.iloc[-1]

        payload["summary"].append(
            {
                "combustible": fuel,
                "fecha": latest["fecha"].strftime("%d/%m/%Y"),
                "precio": round(float(latest["precio"]), 2),
                "cambio_7d": None if pd.isna(latest["prev_7"]) else round(float(latest["precio"] - latest["prev_7"]), 2),
                "cambio_30d": None if pd.isna(latest["prev_30"]) else round(float(latest["precio"] - latest["prev_30"]), 2),
            }
        )

        payload["series"][fuel] = [
            {"fecha": d.strftime("%Y-%m-%d"), "precio": round(float(p), 4)}
            for d, p in zip(sub["fecha"], sub["precio"])
        ]

    return payload


def build_html(payload: dict) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)
    html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Precios de combustibles en Guatemala</title>
<style>
:root {
  --accent: __ACCENT__;
  --green: __GREEN__;
  --bg: __BG__;
  --text: __TEXT__;
  --muted: __MUTED__;
  --grid: __GRID__;
  --border: #d8d2c6;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, Arial, sans-serif;
}
.wrapper {
  max-width: 1280px;
  margin: 0 auto;
  padding: 18px 22px 40px;
}
.topbar {
  border-top: 6px solid var(--accent);
  padding-top: 14px;
  margin-bottom: 18px;
}
h1 {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 34px;
  line-height: 1.1;
  margin: 0 0 8px 0;
  letter-spacing: -0.02em;
}
.meta {
  font-size: 13px;
  color: var(--muted);
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}
.panel {
  background: rgba(255,255,255,.55);
  border: 1px solid var(--border);
}
.main-panel {
  padding: 14px 14px 8px;
}
.controls {
  display:flex;
  justify-content: space-between;
  gap:12px;
  flex-wrap: wrap;
  align-items:center;
  margin-bottom: 8px;
}
.tab-row, .range-row {
  display:flex;
  flex-wrap: wrap;
  gap:0;
}
.tab-btn, .range-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text);
  padding: 10px 14px;
  font-size: 14px;
  cursor: pointer;
  transition: .15s ease;
  margin-right:-1px;
}
.tab-btn.active, .range-btn.active {
  color:#fff;
  background: var(--accent);
  border-color: var(--accent);
}
.tab-btn:hover, .range-btn:hover { background:#f3efe7; }
.tab-btn.active:hover, .range-btn.active:hover { background: var(--accent); }
.chart-title {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 16px;
  margin: 10px 0 2px;
}
.chart-subtitle {
  font-size: 13px;
  color: var(--muted);
  margin-bottom: 6px;
}
#chart {
  width: 100%;
  height: 560px;
}
.sidebar {
  padding: 0;
}
.kpi {
  border-bottom:1px solid var(--border);
  padding: 14px 16px;
}
.kpi:last-child { border-bottom:none; }
.kpi-label {
  font-size: 12px;
  text-transform: uppercase;
  color: var(--muted);
  letter-spacing: .05em;
  margin-bottom: 6px;
}
.kpi-value {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 30px;
  line-height:1;
}
.kpi-delta {
  margin-top: 8px;
  font-size: 14px;
}
.delta-up { color: #147a43; }
.delta-down { color: #a12a1c; }
.delta-flat { color: var(--muted); }
.summary-section {
  margin-top: 20px;
}
.section-head {
  display:flex;
  justify-content:space-between;
  align-items:end;
  gap:12px;
  margin-bottom: 8px;
}
.section-title {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 22px;
  margin: 0;
}
.section-note {
  font-size: 13px;
  color: var(--muted);
}
table {
  width:100%;
  border-collapse: collapse;
  background: rgba(255,255,255,.55);
  border:1px solid var(--border);
}
thead th {
  text-align:left;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
  padding: 10px 12px;
  border-bottom:1px solid var(--border);
}
tbody td {
  padding: 12px;
  border-bottom:1px solid #e8e1d7;
  font-size: 14px;
}
tbody tr:last-child td { border-bottom:none; }
.badge {
  display:inline-block;
  padding:2px 7px;
  background:#fff;
  border:1px solid var(--border);
  font-size:12px;
}
@media (max-width: 1000px) {
  .layout { grid-template-columns: 1fr; }
  #chart { height: 460px; }
}
@media (max-width: 640px) {
  .wrapper { padding: 14px 12px 28px; }
  h1 { font-size: 28px; }
  .tab-btn, .range-btn { padding: 9px 11px; font-size:13px; }
  #chart { height: 390px; }
}
</style>
</head>
<body>
<div class="wrapper">
  <div class="topbar">
    <h1>Precios de combustibles en Guatemala</h1>
    <div class="meta">
      <div><strong>Actualizado:</strong> <span id="lastUpdate">__LAST_UPDATE__</span></div>
      <div><strong>Fuente:</strong> Ministerio de Energía y Minas de Guatemala — mem.gob.gt</div>
    </div>
  </div>

  <div class="layout">
    <div class="panel main-panel">
      <div class="controls">
        <div class="tab-row" id="fuelTabs"></div>
        <div class="range-row" id="rangeTabs"></div>
      </div>
      <div class="chart-title" id="chartTitle">Serie de tiempo</div>
      <div class="chart-subtitle" id="chartSubtitle"></div>
      <div id="chart"></div>
    </div>

    <div class="panel sidebar">
      <div class="kpi">
        <div class="kpi-label">Combustible seleccionado</div>
        <div class="kpi-value" id="kpiFuel">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Último precio</div>
        <div class="kpi-value" id="kpiPrice">—</div>
        <div class="kpi-delta" id="kpiDate">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Cambio 7 días</div>
        <div class="kpi-value" id="kpi7d">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Cambio 30 días</div>
        <div class="kpi-value" id="kpi30d">—</div>
      </div>
    </div>
  </div>

  <div class="summary-section">
    <div class="section-head">
      <h2 class="section-title">Últimos valores</h2>
      <div class="section-note"></div>
    </div>
    <table>
      <thead>
        <tr>
          <th>Combustible</th>
          <th>Último precio</th>
          <th>Cambio 7 días</th>
          <th>Cambio 30 días</th>
          <th>Fecha</th>
        </tr>
      </thead>
      <tbody id="summaryBody"></tbody>
    </table>
  </div>
</div>

<script>__PLOTLY_JS__</script>
<script>
const PAYLOAD = __PAYLOAD_JSON__;
const ORDER = ["Superior", "Regular", "Diésel"];
const RANGE_OPTIONS = [
  { key: "1M", days: 31 },
  { key: "3M", days: 92 },
  { key: "6M", days: 183 },
  { key: "1A", days: 365 },
  { key: "2A", days: 730 },
  { key: "3A", days: 1095 },
  { key: "5A", days: 1825 },
  { key: "Todo", days: null }
];

let currentFuel = ORDER.find(f => PAYLOAD.series[f] && PAYLOAD.series[f].length) || null;
let currentRange = "1A";

const MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

function formatDateSpanish(date) {
  const d = new Date(date);
  return `${String(d.getDate()).padStart(2, "0")} ${MONTHS_ES[d.getMonth()]} ${d.getFullYear()}`;
}

function buildSpanishTicks(series) {
  if (!series.length) return { tickvals: [], ticktext: [] };
  const first = series[0].fecha;
  const last = series[series.length - 1].fecha;
  const totalMonths = (last.getFullYear() - first.getFullYear()) * 12 + (last.getMonth() - first.getMonth()) + 1;
  let stepMonths = 1;
  if (totalMonths > 72) stepMonths = 12;
  else if (totalMonths > 36) stepMonths = 6;
  else if (totalMonths > 18) stepMonths = 3;
  else if (totalMonths > 8) stepMonths = 2;

  const tickvals = [];
  const ticktext = [];
  const cursor = new Date(first.getFullYear(), first.getMonth(), 1);
  while (cursor <= last) {
    tickvals.push(new Date(cursor).toISOString().slice(0, 10));
    const label = stepMonths >= 12
      ? `${MONTHS_ES[cursor.getMonth()]} ${cursor.getFullYear()}`
      : `${MONTHS_ES[cursor.getMonth()]} ${String(cursor.getFullYear()).slice(-2)}`;
    ticktext.push(label);
    cursor.setMonth(cursor.getMonth() + stepMonths);
  }
  return { tickvals, ticktext };
}

function money(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return "Q" + Number(v).toFixed(2);
}

function signedMoney(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  const sign = n > 0 ? "+" : "";
  return sign + "Q" + n.toFixed(2);
}

function deltaClass(v) {
  if (v === null || v === undefined || Number.isNaN(v) || Number(v) === 0) return "delta-flat";
  return Number(v) > 0 ? "delta-up" : "delta-down";
}

function buildFuelTabs() {
  const el = document.getElementById("fuelTabs");
  el.innerHTML = "";
  ORDER.forEach(fuel => {
    if (!PAYLOAD.series[fuel]) return;
    const btn = document.createElement("button");
    btn.className = "tab-btn" + (fuel === currentFuel ? " active" : "");
    btn.textContent = fuel;
    btn.onclick = () => {
      currentFuel = fuel;
      buildFuelTabs();
      render();
    };
    el.appendChild(btn);
  });
}

function buildRangeTabs() {
  const el = document.getElementById("rangeTabs");
  el.innerHTML = "";
  RANGE_OPTIONS.forEach(opt => {
    const btn = document.createElement("button");
    btn.className = "range-btn" + (opt.key === currentRange ? " active" : "");
    btn.textContent = opt.key;
    btn.onclick = () => {
      currentRange = opt.key;
      buildRangeTabs();
      render();
    };
    el.appendChild(btn);
  });
}

function getFilteredSeries() {
  const series = (PAYLOAD.series[currentFuel] || []).map(d => ({
    fecha: new Date(d.fecha + "T00:00:00"),
    precio: Number(d.precio)
  }));
  if (!series.length) return [];
  const option = RANGE_OPTIONS.find(x => x.key === currentRange);
  if (!option || option.days === null) return series;
  const maxDate = series[series.length - 1].fecha;
  const minDate = new Date(maxDate.getTime() - option.days * 24 * 60 * 60 * 1000);
  return series.filter(d => d.fecha >= minDate);
}

function renderChart(series) {
  const x = series.map(d => d.fecha.toISOString().slice(0,10));
  const y = series.map(d => d.precio);

  const hovertext = series.map(d => formatDateSpanish(d.fecha));
  const ticks = buildSpanishTicks(series);

  const trace = {
    x, y,
    type: "scatter",
    mode: "lines",
    hovertext,
    hovertemplate: "<b>%{hovertext}</b><br>Precio: Q%{y:.2f}<extra></extra>",
    line: { color: "__GREEN__", width: 3 }
  };

  const layout = {
    paper_bgcolor: "__BG__",
    plot_bgcolor: "__BG__",
    margin: { t: 10, r: 20, b: 45, l: 60 },
    showlegend: false,
    xaxis: {
      showgrid: true,
      gridcolor: "__GRID__",
      zeroline: false,
      tickfont: { size: 12, color: "__MUTED__" },
      ticks: "",
      tickmode: "array",
      tickvals: ticks.tickvals,
      ticktext: ticks.ticktext
    },
    yaxis: {
      showgrid: true,
      gridcolor: "__GRID__",
      zeroline: false,
      tickprefix: "Q",
      separatethousands: false,
      tickfont: { size: 12, color: "__MUTED__" }
    },
    font: {
      family: "Inter, Arial, sans-serif",
      color: "__TEXT__"
    },
    hoverlabel: {
      bgcolor: "#ffffff",
      bordercolor: "__GRID__",
      font: { color: "__TEXT__" }
    }
  };

  Plotly.newPlot("chart", [trace], layout, {
    responsive: true,
    displayModeBar: false
  });
}

function renderKpis() {
  const summary = (PAYLOAD.summary || []).find(x => x.combustible === currentFuel);
  document.getElementById("kpiFuel").textContent = currentFuel || "—";
  document.getElementById("kpiPrice").textContent = summary ? money(summary.precio) : "—";
  document.getElementById("kpiDate").textContent = summary ? ("Dato válido más reciente: " + summary.fecha) : "—";

  const kpi7 = document.getElementById("kpi7d");
  const kpi30 = document.getElementById("kpi30d");
  if (summary) {
    kpi7.textContent = signedMoney(summary.cambio_7d);
    kpi30.textContent = signedMoney(summary.cambio_30d);
    kpi7.className = "kpi-value " + deltaClass(summary.cambio_7d);
    kpi30.className = "kpi-value " + deltaClass(summary.cambio_30d);
  } else {
    kpi7.textContent = "—";
    kpi30.textContent = "—";
    kpi7.className = "kpi-value";
    kpi30.className = "kpi-value";
  }
}

function renderSummaryTable() {
  const body = document.getElementById("summaryBody");
  const rows = (PAYLOAD.summary || [])
    .slice()
    .sort((a, b) => ORDER.indexOf(a.combustible) - ORDER.indexOf(b.combustible))
    .map(s => `
      <tr>
        <td><span class="badge">${s.combustible}</span></td>
        <td>${money(s.precio)}</td>
        <td class="${deltaClass(s.cambio_7d)}">${signedMoney(s.cambio_7d)}</td>
        <td class="${deltaClass(s.cambio_30d)}">${signedMoney(s.cambio_30d)}</td>
        <td>${s.fecha}</td>
      </tr>
    `)
    .join("");
  body.innerHTML = rows || '<tr><td colspan="5">Sin datos.</td></tr>';
}

function render() {
  const series = getFilteredSeries();
  document.getElementById("chartTitle").textContent = currentFuel ? currentFuel : "Serie de tiempo";
  document.getElementById("chartSubtitle").textContent = "";
  renderChart(series);
  renderKpis();
}

buildFuelTabs();
buildRangeTabs();
renderSummaryTable();
render();
</script>
</body>
</html>"""
    replacements = {
        "__ACCENT__": ACCENT,
        "__GREEN__": GREEN,
        "__BG__": BG,
        "__TEXT__": TEXT,
        "__MUTED__": MUTED,
        "__GRID__": GRID,
        "__LAST_UPDATE__": payload.get("last_update") or "—",
        "__PAYLOAD_JSON__": payload_json,
        "__PLOTLY_JS__": get_plotlyjs(),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


def main(input_csv: str | Path = INPUT_CSV, output_html: str | Path = OUTPUT_HTML) -> Path:
    df = prepare_data(input_csv)
    payload = build_payload(df)
    html = build_html(payload)
    output_path = Path(output_html)
    output_path.write_text(html, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    out = main()
    print(f"Dashboard generado: {out}")
