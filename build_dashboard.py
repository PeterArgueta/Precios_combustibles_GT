from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from plotly.offline import get_plotlyjs

INPUT_CSV  = "precios_historicos.csv"
OUTPUT_HTML = "index.html"

ACCENT = "#d62d20"
BG     = "#f8f6f0"
TEXT   = "#1f1f1f"
MUTED  = "#6a6a6a"
GRID   = "#d9d5cc"

# ── Colores por combustible ───────────────────────────────────────────────────
FUEL_COLORS = {
    "Superior": "#d62d20",  # Rojo
    "Regular":  "#2a7a3b",  # Verde
    "Diésel":   "#1a5fa8",  # Azul
}

ORDER = ["Superior", "Regular", "Diésel"]


# ── ETL ───────────────────────────────────────────────────────────────────────

def prepare_data(csv_path: str | Path = INPUT_CSV) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["fecha"]       = pd.to_datetime(df["fecha"], errors="coerce")
    df["precio"]      = pd.to_numeric(df["precio"], errors="coerce")
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

        sub["prev_7"]  = sub["precio"].shift(7)
        sub["prev_30"] = sub["precio"].shift(30)
        latest = sub.iloc[-1]

        payload["summary"].append({
            "combustible": fuel,
            "fecha":       latest["fecha"].strftime("%d/%m/%Y"),
            "precio":      round(float(latest["precio"]), 2),
            "cambio_7d":   None if pd.isna(latest["prev_7"])
                           else round(float(latest["precio"] - latest["prev_7"]), 2),
            "cambio_30d":  None if pd.isna(latest["prev_30"])
                           else round(float(latest["precio"] - latest["prev_30"]), 2),
        })

        payload["series"][fuel] = [
            {"fecha": d.strftime("%Y-%m-%d"), "precio": round(float(p), 4)}
            for d, p in zip(sub["fecha"], sub["precio"])
        ]

    return payload


# ── HTML ──────────────────────────────────────────────────────────────────────

def build_html(payload: dict) -> str:
    payload_json = json.dumps(payload, ensure_ascii=False)

    # Colores serializados para inyectar en JS
    fuel_colors_json = json.dumps(FUEL_COLORS, ensure_ascii=False)

    html = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Precios de combustibles en Guatemala</title>
<style>
:root {
  --accent: __ACCENT__;
  --bg:     __BG__;
  --text:   __TEXT__;
  --muted:  __MUTED__;
  --grid:   __GRID__;
  --border: #d8d2c6;
  --red:    #d62d20;
  --green:  #2a7a3b;
  --blue:   #1a5fa8;
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

/* ── Header ── */
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

/* ── Layout ── */
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

.main-panel { padding: 14px 14px 8px; }

/* ── Controls ── */
.controls {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 8px;
}

.tab-row, .range-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}

.tab-btn, .range-btn {
  border: 1px solid var(--border);
  background: #fff;
  color: var(--text);
  padding: 10px 14px;
  font-size: 14px;
  cursor: pointer;
  transition: .15s ease;
  margin-right: -1px;
}

.tab-btn.active, .range-btn.active {
  color: #fff;
  background: var(--accent);
  border-color: var(--accent);
}

/* Combinado activo usa un azul oscuro neutro */
.tab-btn.active-combinado {
  color: #fff;
  background: #2c3e50;
  border-color: #2c3e50;
}

/* Colores activos por combustible */
.tab-btn.active-super   { color:#fff; background: var(--red);   border-color: var(--red);   }
.tab-btn.active-regular { color:#fff; background: var(--green); border-color: var(--green); }
.tab-btn.active-diesel  { color:#fff; background: var(--blue);  border-color: var(--blue);  }

.tab-btn:hover, .range-btn:hover { background: #f3efe7; }
.tab-btn.active:hover,
.tab-btn.active-combinado:hover,
.tab-btn.active-super:hover,
.tab-btn.active-regular:hover,
.tab-btn.active-diesel:hover { opacity: .88; }

/* ── Chart ── */
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

#chart { width: 100%; height: 560px; }

/* ── Sidebar ── */
.sidebar { padding: 0; }

.kpi {
  border-bottom: 1px solid var(--border);
  padding: 14px 16px;
}

.kpi:last-child { border-bottom: none; }

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
  line-height: 1;
}

.kpi-delta { margin-top: 8px; font-size: 14px; }

.delta-up   { color: #147a43; }
.delta-down { color: #a12a1c; }
.delta-flat { color: var(--muted); }

/* KPI combinado: minilista */
.kpi-multi { font-family: Georgia, serif; }
.kpi-multi-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 5px 0;
  border-bottom: 1px solid #ece8e2;
  font-size: 15px;
}
.kpi-multi-row:last-child { border-bottom: none; }
.kpi-multi-label { font-size: 13px; color: var(--muted); }
.kpi-multi-val   { font-weight: 600; }

/* ── Summary table ── */
.summary-section { margin-top: 20px; }

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 12px;
  margin-bottom: 8px;
}

.section-title {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 22px;
  margin: 0;
}

.section-note { font-size: 13px; color: var(--muted); }

table {
  width: 100%;
  border-collapse: collapse;
  background: rgba(255,255,255,.55);
  border: 1px solid var(--border);
}

thead th {
  text-align: left;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--muted);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}

tbody td {
  padding: 12px;
  border-bottom: 1px solid #e8e1d7;
  font-size: 14px;
}

tbody tr:last-child td { border-bottom: none; }

.badge {
  display: inline-block;
  padding: 2px 7px;
  background: #fff;
  border: 1px solid var(--border);
  font-size: 12px;
}

/* ── Context panel ── */
.context-section { margin-top: 20px; }

.context-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
  margin-top: 10px;
}

.context-card {
  background: rgba(255,255,255,.7);
  border: 1px solid var(--border);
  border-left: 4px solid #ccc;
  padding: 14px 16px;
}

.context-card.card-super   { border-left-color: var(--red);   }
.context-card.card-regular { border-left-color: var(--green); }
.context-card.card-diesel  { border-left-color: var(--blue);  }

.context-fuel {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .07em;
  font-weight: 700;
  margin-bottom: 6px;
}

.context-status {
  font-family: Georgia, "Times New Roman", serif;
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 5px;
}

.context-detail {
  font-size: 13px;
  color: var(--muted);
}

/* ── Responsive ── */
@media (max-width: 1000px) {
  .layout { grid-template-columns: 1fr; }
  #chart  { height: 460px; }
}

@media (max-width: 640px) {
  .wrapper { padding: 14px 12px 28px; }
  h1 { font-size: 28px; }
  .tab-btn, .range-btn { padding: 9px 11px; font-size: 13px; }
  #chart { height: 390px; }
}
</style>
</head>
<body>
<div class="wrapper">

  <!-- ── Header ── -->
  <div class="topbar">
    <h1>Precios de combustibles en Guatemala</h1>
    <div class="meta">
      <div><strong>Actualizado:</strong> <span id="lastUpdate">__LAST_UPDATE__</span></div>
      <div><strong>Fuente:</strong> Ministerio de Energía y Minas de Guatemala — mem.gob.gt</div>
    </div>
  </div>

  <!-- ── Main layout ── -->
  <div class="layout">

    <!-- Chart panel -->
    <div class="panel main-panel">
      <div class="controls">
        <div class="tab-row"   id="fuelTabs"></div>
        <div class="range-row" id="rangeTabs"></div>
      </div>
      <div class="chart-title"    id="chartTitle">Serie de tiempo</div>
      <div class="chart-subtitle" id="chartSubtitle"></div>
      <div id="chart"></div>
    </div>

    <!-- Sidebar KPIs -->
    <div class="panel sidebar" id="sidebar">
      <div class="kpi">
        <div class="kpi-label">Combustible seleccionado</div>
        <div class="kpi-value" id="kpiFuel">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Último precio</div>
        <div class="kpi-value" id="kpiPrice">—</div>
        <div class="kpi-delta"  id="kpiDate">—</div>
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

  </div><!-- /.layout -->

  <!-- ── Summary table ── -->
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

  <!-- ── Context panel ── -->
  <div class="context-section">
    <div class="section-head">
      <h2 class="section-title" id="contextTitle">Cambio del período</h2>
      <div class="section-note" id="contextNote"></div>
    </div>
    <div class="context-cards" id="contextCards"></div>
  </div>

</div><!-- /.wrapper -->

<script>__PLOTLY_JS__</script>
<script>
const PAYLOAD     = __PAYLOAD_JSON__;
const FUEL_COLORS = __FUEL_COLORS_JSON__;
const ORDER       = ["Superior", "Regular", "Diésel"];

const CARD_CLASS  = {
  "Superior": "card-super",
  "Regular":  "card-regular",
  "Diésel":   "card-diesel"
};

const RANGE_OPTIONS = [
  { key: "1M",   days: 31   },
  { key: "3M",   days: 92   },
  { key: "6M",   days: 183  },
  { key: "1A",   days: 365  },
  { key: "2A",   days: 730  },
  { key: "3A",   days: 1095 },
  { key: "5A",   days: 1825 },
  { key: "Todo", days: null  }
];

let currentFuel  = ORDER.find(f => PAYLOAD.series[f]?.length) || null;
let currentRange = "1A";

const MONTHS_ES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"];

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDateSpanish(date) {
  const d = new Date(date);
  return `${String(d.getDate()).padStart(2,"0")} ${MONTHS_ES[d.getMonth()]} ${d.getFullYear()}`;
}

function money(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return "Q" + Number(v).toFixed(2);
}

function signedMoney(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const n = Number(v);
  return (n >= 0 ? "+" : "") + "Q" + n.toFixed(2);
}

function deltaClass(v) {
  if (v === null || v === undefined || Number.isNaN(v) || Number(v) === 0) return "delta-flat";
  return Number(v) > 0 ? "delta-up" : "delta-down";
}

function parseSeries(fuel) {
  return (PAYLOAD.series[fuel] || []).map(d => ({
    fecha:  new Date(d.fecha + "T00:00:00"),
    precio: Number(d.precio)
  }));
}

function filterSeries(series) {
  if (!series.length) return [];
  const option = RANGE_OPTIONS.find(x => x.key === currentRange);
  if (!option || option.days === null) return series;
  const maxDate = series[series.length - 1].fecha;
  const minDate = new Date(maxDate.getTime() - option.days * 86400000);
  return series.filter(d => d.fecha >= minDate);
}

function buildSpanishTicks(series) {
  if (!series.length) return { tickvals: [], ticktext: [] };
  const first = series[0].fecha;
  const last  = series[series.length - 1].fecha;
  const totalMonths = (last.getFullYear() - first.getFullYear()) * 12
                    + (last.getMonth() - first.getMonth()) + 1;
  let stepMonths = 1;
  if      (totalMonths > 72) stepMonths = 12;
  else if (totalMonths > 36) stepMonths = 6;
  else if (totalMonths > 18) stepMonths = 3;
  else if (totalMonths > 8)  stepMonths = 2;

  const tickvals = [], ticktext = [];
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

// ── Chart ────────────────────────────────────────────────────────────────────

function renderChart() {
  const isCombinado = (currentFuel === "Combinado");
  const fuels = isCombinado ? ORDER : [currentFuel];

  const traces = fuels.map(fuel => {
    const series  = filterSeries(parseSeries(fuel));
    const x       = series.map(d => d.fecha.toISOString().slice(0, 10));
    const y       = series.map(d => d.precio);
    const hover   = series.map(d => formatDateSpanish(d.fecha));
    return {
      x, y,
      name:          fuel,
      type:          "scatter",
      mode:          "lines",
      hovertext:     hover,
      hovertemplate: `<b>${fuel}</b><br>%{hovertext}<br>Q%{y:.2f}<extra></extra>`,
      line:          { color: FUEL_COLORS[fuel], width: isCombinado ? 2.5 : 3 }
    };
  });

  // Use the first available series for tick generation
  const refSeries = filterSeries(parseSeries(fuels[0]));
  const ticks     = buildSpanishTicks(refSeries);

  const layout = {
    paper_bgcolor: "__BG__",
    plot_bgcolor:  "__BG__",
    margin:        { t: 10, r: 20, b: 45, l: 60 },
    showlegend:    isCombinado,
    legend:        { orientation: "h", y: -0.12, x: 0.5, xanchor: "center",
                     font: { size: 13 } },
    xaxis: {
      showgrid:  true,
      gridcolor: "__GRID__",
      zeroline:  false,
      tickfont:  { size: 12, color: "__MUTED__" },
      ticks:     "",
      tickmode:  "array",
      tickvals:  ticks.tickvals,
      ticktext:  ticks.ticktext
    },
    yaxis: {
      showgrid:  true,
      gridcolor: "__GRID__",
      zeroline:  false,
      tickprefix:"Q",
      tickfont:  { size: 12, color: "__MUTED__" }
    },
    font:     { family: "Inter, Arial, sans-serif", color: "__TEXT__" },
    hoverlabel: { bgcolor: "#ffffff", bordercolor: "__GRID__",
                  font: { color: "__TEXT__" } }
  };

  Plotly.newPlot("chart", traces, layout, { responsive: true, displayModeBar: false });
}

// ── Sidebar KPIs ─────────────────────────────────────────────────────────────

function renderKpis() {
  const isCombinado = (currentFuel === "Combinado");
  const sidebar = document.getElementById("sidebar");

  if (!isCombinado) {
    // Single fuel — original layout
    sidebar.innerHTML = `
      <div class="kpi">
        <div class="kpi-label">Combustible seleccionado</div>
        <div class="kpi-value" id="kpiFuel">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Último precio</div>
        <div class="kpi-value" id="kpiPrice">—</div>
        <div class="kpi-delta"  id="kpiDate">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Cambio 7 días</div>
        <div class="kpi-value" id="kpi7d">—</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Cambio 30 días</div>
        <div class="kpi-value" id="kpi30d">—</div>
      </div>`;

    const summary = (PAYLOAD.summary || []).find(x => x.combustible === currentFuel);
    const color   = FUEL_COLORS[currentFuel] || "__TEXT__";

    document.getElementById("kpiFuel").style.color = color;
    document.getElementById("kpiFuel").textContent = currentFuel || "—";
    document.getElementById("kpiPrice").textContent = summary ? money(summary.precio) : "—";
    document.getElementById("kpiDate").textContent  = summary
      ? "Dato válido más reciente: " + summary.fecha : "—";

    const kpi7  = document.getElementById("kpi7d");
    const kpi30 = document.getElementById("kpi30d");
    if (summary) {
      kpi7.textContent  = signedMoney(summary.cambio_7d);
      kpi30.textContent = signedMoney(summary.cambio_30d);
      kpi7.className    = "kpi-value " + deltaClass(summary.cambio_7d);
      kpi30.className   = "kpi-value " + deltaClass(summary.cambio_30d);
    } else {
      kpi7.textContent  = "—";
      kpi30.textContent = "—";
    }

  } else {
    // Combinado — compact multi-row list
    const rows = ORDER.map(fuel => {
      const summary = (PAYLOAD.summary || []).find(x => x.combustible === fuel);
      const price   = summary ? money(summary.precio) : "—";
      const d30     = summary ? signedMoney(summary.cambio_30d) : "—";
      const cls     = summary ? deltaClass(summary.cambio_30d) : "";
      return `
        <div class="kpi-multi-row">
          <div>
            <div class="kpi-multi-label">${fuel}</div>
            <div class="kpi-multi-val" style="color:${FUEL_COLORS[fuel]}">${price}</div>
          </div>
          <div class="${cls}" style="font-size:14px;font-weight:600">${d30}</div>
        </div>`;
    }).join("");

    sidebar.innerHTML = `
      <div class="kpi">
        <div class="kpi-label">Combustibles combinados</div>
        <div class="kpi-multi">${rows}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label" style="font-size:11px">Último dato más reciente</div>
        <div style="font-size:13px;color:var(--muted);margin-top:4px">
          ${PAYLOAD.last_update || "—"}
        </div>
      </div>`;
  }
}

// ── Context panel (Cambio del período) ───────────────────────────────────────

function renderContextPanel() {
  const isCombinado = (currentFuel === "Combinado");
  const fuels       = isCombinado ? ORDER : [currentFuel];

  // Dynamic title
  document.getElementById("contextTitle").textContent =
    `Cambio del período: ${currentRange}`;
  document.getElementById("contextNote").textContent =
    "Último precio vs. promedio del período seleccionado";

  const cards = fuels.map(fuel => {
    const allSeries = parseSeries(fuel);
    const filtered  = filterSeries(allSeries);
    if (filtered.length < 2) return "";

    const lastPrice = filtered[filtered.length - 1].precio;
    const avg       = filtered.reduce((s, d) => s + d.precio, 0) / filtered.length;
    const diff      = lastPrice - avg;
    const pct       = (diff / avg) * 100;

    // Threshold: ±0.5% se considera "en el promedio"
    let icon, label, cls;
    if (Math.abs(pct) < 0.5) {
      icon = "≈"; label = "En el promedio del período"; cls = "delta-flat";
    } else if (diff > 0) {
      icon = "▲"; label = "Por arriba del promedio";   cls = "delta-up";
    } else {
      icon = "▼"; label = "Por abajo del promedio";    cls = "delta-down";
    }

    const sign = diff >= 0 ? "+" : "";

    return `
      <div class="context-card ${CARD_CLASS[fuel]}">
        <div class="context-fuel" style="color:${FUEL_COLORS[fuel]}">${fuel}</div>
        <div class="context-status ${cls}">${icon} ${label}</div>
        <div class="context-detail">
          Último: <strong>${money(lastPrice)}</strong> —
          Promedio ${currentRange}: <strong>${money(avg)}</strong>
          &nbsp;(${sign}${money(diff)}, ${sign}${pct.toFixed(1)}%)
        </div>
      </div>`;
  }).join("");

  document.getElementById("contextCards").innerHTML =
    cards || '<p style="color:var(--muted);font-size:14px">Sin datos suficientes para el período.</p>';
}

// ── Summary table ─────────────────────────────────────────────────────────────

function renderSummaryTable() {
  const body = document.getElementById("summaryBody");
  const rows = (PAYLOAD.summary || [])
    .slice()
    .sort((a, b) => ORDER.indexOf(a.combustible) - ORDER.indexOf(b.combustible))
    .map(s => {
      const color = FUEL_COLORS[s.combustible] || "#333";
      return `
        <tr>
          <td><span class="badge" style="border-left:3px solid ${color};padding-left:8px">${s.combustible}</span></td>
          <td>${money(s.precio)}</td>
          <td class="${deltaClass(s.cambio_7d)}">${signedMoney(s.cambio_7d)}</td>
          <td class="${deltaClass(s.cambio_30d)}">${signedMoney(s.cambio_30d)}</td>
          <td>${s.fecha}</td>
        </tr>`;
    })
    .join("");
  body.innerHTML = rows || '<tr><td colspan="5">Sin datos.</td></tr>';
}

// ── Tab builders ──────────────────────────────────────────────────────────────

function buildFuelTabs() {
  const el = document.getElementById("fuelTabs");
  el.innerHTML = "";

  // Individual fuel buttons
  ORDER.forEach(fuel => {
    if (!PAYLOAD.series[fuel]) return;
    const btn = document.createElement("button");
    const isActive = (fuel === currentFuel);

    let activeClass = "";
    if (isActive) {
      if      (fuel === "Superior") activeClass = "active-super";
      else if (fuel === "Regular")  activeClass = "active-regular";
      else if (fuel === "Diésel")   activeClass = "active-diesel";
    }

    btn.className = "tab-btn" + (activeClass ? " " + activeClass : "");
    btn.textContent = fuel;
    btn.onclick = () => { currentFuel = fuel; render(); };
    el.appendChild(btn);
  });

  // Combinado button
  const hasData = ORDER.some(f => PAYLOAD.series[f]?.length);
  if (hasData) {
    const btn = document.createElement("button");
    btn.className  = "tab-btn" + (currentFuel === "Combinado" ? " active-combinado" : "");
    btn.textContent = "Combinado";
    btn.onclick = () => { currentFuel = "Combinado"; render(); };
    el.appendChild(btn);
  }
}

function buildRangeTabs() {
  const el = document.getElementById("rangeTabs");
  el.innerHTML = "";
  RANGE_OPTIONS.forEach(opt => {
    const btn = document.createElement("button");
    btn.className   = "range-btn" + (opt.key === currentRange ? " active" : "");
    btn.textContent = opt.key;
    btn.onclick = () => { currentRange = opt.key; buildRangeTabs(); render(); };
    el.appendChild(btn);
  });
}

// ── Main render ───────────────────────────────────────────────────────────────

function render() {
  buildFuelTabs();
  document.getElementById("chartTitle").textContent =
    currentFuel === "Combinado" ? "Los tres combustibles" : (currentFuel || "Serie de tiempo");
  document.getElementById("chartSubtitle").textContent = "";

  renderChart();
  renderKpis();
  renderContextPanel();
}

// ── Init ──────────────────────────────────────────────────────────────────────

buildFuelTabs();
buildRangeTabs();
renderSummaryTable();
render();
</script>
</body>
</html>"""

    replacements = {
        "__ACCENT__":          ACCENT,
        "__BG__":              BG,
        "__TEXT__":            TEXT,
        "__MUTED__":           MUTED,
        "__GRID__":            GRID,
        "__LAST_UPDATE__":     payload.get("last_update") or "—",
        "__PAYLOAD_JSON__":    payload_json,
        "__FUEL_COLORS_JSON__": fuel_colors_json,
        "__PLOTLY_JS__":       get_plotlyjs(),
    }

    for key, value in replacements.items():
        html = html.replace(key, value)

    return html


# ── Entry point ───────────────────────────────────────────────────────────────

def main(
    input_csv:   str | Path = INPUT_CSV,
    output_html: str | Path = OUTPUT_HTML,
) -> Path:
    df      = prepare_data(input_csv)
    payload = build_payload(df)
    html    = build_html(payload)

    output_path = Path(output_html)
    output_path.write_text(html, encoding="utf-8")
    return output_path


if __name__ == "__main__":
    out = main()
    print(f"Dashboard generado: {out}")
