from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Constantes ────────────────────────────────────────────────────────────────

MEM_PAGE_URL    = "https://mem.gob.gt/que-hacemos/hidrocarburos/comercializacion-downstream/precios-combustible-nacionales/"
MEM_API_URL     = "https://mem.gob.gt/wp-json/wp/v2/pages/45428"
OUTPUT_CSV      = "precios_historicos.csv"
EXCEL_URL_CACHE = "last_excel_url.txt"

LOGGER = logging.getLogger(__name__)

# Mapa de nombres en el Excel → nombre canónico del CSV
FUEL_TARGETS = {
    "Gasolina Superior":         "Superior",
    "Gasolina Regular":          "Regular",
    "ACEITE COMBUSTIBLE DIÉSEL": "Diésel",
    "ACEITE COMBUSTIBLE DIESEL": "Diésel",
    "Bunker":                    "Búnker",
    "Búnker":                    "Búnker",
    "GLP":                       "GLP",
}

# Mapa de nombres en la API (HTML embebido) → nombre canónico
API_FUEL_MAP = {
    "gasolina superior":   "Superior",
    "gasolina regular":    "Regular",
    "combustible diesel":  "Diésel",
    "combustible diésel":  "Diésel",
}

# ── Helpers de texto ──────────────────────────────────────────────────────────

def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )

def _norm_text(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    text = _strip_accents(text).lower()
    text = re.sub(r"\s+", " ", text)
    return text

# ── Proxy helper ──────────────────────────────────────────────────────────────

def _get_mem(url: str, session: requests.Session, **kwargs) -> requests.Response:
    """Hace GET a una URL del MEM, usando proxy Cloudflare si está configurado."""
    proxy_base = os.environ.get("CLOUDFLARE_PROXY_URL", "").strip()
    if proxy_base and "mem.gob.gt" in url:
        fetch_url = f"{proxy_base}?url={url}"
        LOGGER.info("Request vía proxy Cloudflare: %s", fetch_url)
    else:
        fetch_url = url
    kwargs.setdefault("stream", False)
    resp = session.get(fetch_url, **kwargs)
    _ = resp.content  # fuerza descarga completa del body
    resp.encoding = "utf-8"
    LOGGER.info("_get_mem | status=%s | bytes=%s", resp.status_code, len(resp.content))
    return resp

# ── Fuente 1: API WordPress REST ──────────────────────────────────────────────

def fetch_api_rows(session: requests.Session) -> pd.DataFrame:
    """Extrae el 'Monitoreo Actual' del endpoint WP REST del MEM."""
    try:
        resp = _get_mem(MEM_API_URL, session, timeout=30)
        resp.raise_for_status()
        raw_text = resp.content.decode("utf-8", errors="replace")
        LOGGER.info("API raw | status=%s | bytes=%s | preview=%s",
                    resp.status_code, len(resp.content), repr(raw_text[:200]))
        data = json.loads(raw_text)
    except Exception as exc:
        LOGGER.warning("API MEM no disponible: %s", exc)
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])

    html = data.get("content", {}).get("rendered", "")
    if not html:
        LOGGER.warning("API MEM: campo content.rendered vacío.")
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])

    soup = BeautifulSoup(html, "html.parser")

    # ── Tipo de cambio ────────────────────────────────────────────────────────
    tipo_cambio: float | None = None
    for text in soup.stripped_strings:
        m = re.search(r"tipo de cambio[^:]*:\s*Q?([\d.]+)", text, re.IGNORECASE)
        if m:
            try:
                tipo_cambio = float(m.group(1))
                break
            except ValueError:
                pass

    # ── Primera tabla = modalidad autoservicio ────────────────────────────────
    tables = soup.find_all("table")
    if not tables:
        LOGGER.warning("API MEM: no se encontraron tablas en content.rendered.")
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])

    table     = tables[0]
    rows_html = table.find_all("tr")
    if not rows_html:
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])

    # ── Detectar columna "Monitoreo Actual" y su fecha ───────────────────────
    header_cells   = [td.get_text(strip=True) for td in rows_html[0].find_all(["td", "th"])]
    fecha_actual: pd.Timestamp | None = None
    actual_col_idx: int | None        = None

    for i, cell in enumerate(header_cells):
        m = re.search(r"Monitoreo Actual[^:]*:\s*(\d{2}/\d{2}/\d{4})", cell, re.IGNORECASE)
        if m:
            try:
                fecha_actual   = pd.to_datetime(m.group(1), format="%d/%m/%Y")
                actual_col_idx = i
                break
            except ValueError:
                pass

    if fecha_actual is None or actual_col_idx is None:
        LOGGER.warning("API MEM: no se detectó columna 'Monitoreo Actual' con fecha.")
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])

    # ── Extraer filas de datos ────────────────────────────────────────────────
    records: list[dict] = []
    for tr in rows_html[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) <= actual_col_idx:
            continue
        fuel = API_FUEL_MAP.get(_norm_text(cells[0]))
        if fuel is None:
            continue
        price_str = cells[actual_col_idx].replace("Q", "").strip()
        try:
            price = float(price_str)
        except ValueError:
            continue
        records.append({
            "fecha":       fecha_actual,
            "combustible": fuel,
            "precio":      price,
            "tipo_cambio": tipo_cambio,
        })

    if not records:
        LOGGER.warning("API MEM: tablas encontradas pero sin filas de combustibles reconocidos.")
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])

    df = pd.DataFrame(records)
    LOGGER.info(
        "API MEM: %s filas extraídas para fecha %s (tipo_cambio=Q%s)",
        len(df), fecha_actual.strftime("%Y-%m-%d"), tipo_cambio,
    )
    return df

# ── Fuente 2: Excel oficial MEM ───────────────────────────────────────────────

def _load_cached_excel_url() -> str | None:
    """Devuelve la URL del Excel de la última corrida exitosa, o None si no existe."""
    path = Path(EXCEL_URL_CACHE)
    if path.exists():
        url = path.read_text(encoding="utf-8").strip()
        return url if url else None
    return None


def _find_excel_url_raw(session: requests.Session) -> str:
    """Lógica interna para obtener la URL del Excel. No cachea."""

    # Intento 1: extraer URL directamente del JSON de la API
    try:
        resp = _get_mem(MEM_API_URL, session, timeout=30)
        resp.raise_for_status()
        data = json.loads(resp.content.decode("utf-8", errors="replace"))
        html = data.get("content", {}).get("rendered", "")
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).strip()
            if href.lower().endswith((".xlsx", ".xls")) and "precios" in href.lower():
                LOGGER.info("URL del Excel obtenida vía API: %s", href)
                return href
    except Exception as exc:
        LOGGER.warning("No se pudo extraer URL del Excel vía API: %s", exc)

    # Intento 2: scraping de la página HTML
    LOGGER.info("Fallback: buscando Excel en página HTML del MEM…")
    response = _get_mem(MEM_PAGE_URL, session, timeout=60)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    matches: list[tuple[int, str, str]] = []
    for anchor in soup.find_all("a", href=True):
        href  = str(anchor["href"]).strip()
        text  = anchor.get_text(" ", strip=True)
        if not href or not text:
            continue
        if not (href.lower().endswith(".xlsx") or href.lower().endswith(".xls")):
            continue
        text_norm = _norm_text(text)
        score = 0
        if "precios diarios de combustibles" in text_norm:
            score += 100
        elif "precios diarios" in text_norm:
            score += 50
        if "combustibles" in text_norm:
            score += 20
        if score > 0:
            matches.append((score, text, urljoin(MEM_PAGE_URL, href)))

    if not matches:
        raise RuntimeError(
            "No se encontró enlace al Excel de precios diarios en la página del MEM."
        )

    matches.sort(key=lambda x: x[0], reverse=True)
    best = matches[0]
    LOGGER.info("Excel detectado (HTML): texto='%s' | url=%s", best[1], best[2])
    return best[2]


def find_excel_url(session: requests.Session) -> str:
    """Obtiene la URL del Excel y la cachea para futuros fallbacks."""
    url = _find_excel_url_raw(session)
    try:
        Path(EXCEL_URL_CACHE).write_text(url, encoding="utf-8")
    except OSError as exc:
        LOGGER.warning("No se pudo cachear la URL del Excel: %s", exc)
    return url


def download_excel_bytes(url: str, session: requests.Session) -> bytes:
    """Descarga el Excel usando proxy Cloudflare si está configurado."""
    proxy_base = os.environ.get("CLOUDFLARE_PROXY_URL", "").strip()
    if proxy_base:
        fetch_url = f"{proxy_base}?url={url}"
        LOGGER.info("Descargando Excel vía proxy Cloudflare: %s", fetch_url)
    else:
        fetch_url = url
        LOGGER.info("Descargando Excel directo: %s", fetch_url)
    response = session.get(fetch_url, timeout=120)
    response.raise_for_status()
    return response.content


def _find_header_row(raw: pd.DataFrame) -> int:
    for idx in range(min(len(raw), 40)):
        row = [_norm_text(v) for v in raw.iloc[idx].tolist()]
        if "fecha" in row and ("tipo de cambio" in row or "tipo cambio" in row):
            return idx
    raise RuntimeError(
        "No se encontró fila de encabezados (FECHA + Tipo de Cambio) en el Excel del MEM."
    )


def parse_workbook(excel_bytes: bytes) -> pd.DataFrame:
    workbook = pd.ExcelFile(io.BytesIO(excel_bytes))
    frames: list[pd.DataFrame] = []

    for sheet_name in workbook.sheet_names:
        raw = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
        if raw.empty:
            continue

        header_row    = _find_header_row(raw)
        header_values = raw.iloc[header_row].tolist()

        columns = [
            str(v).strip() if (v is not None and not (isinstance(v, float) and pd.isna(v)))
            else f"unnamed_{i}"
            for i, v in enumerate(header_values)
        ]

        data = raw.iloc[header_row + 2:].copy()  # salta fila de unidades
        data.columns = columns

        rename_map: dict[str, str] = {}
        for col in data.columns:
            norm = _norm_text(col)
            if norm == "fecha":
                rename_map[col] = "fecha"
            elif norm in {"tipo de cambio", "tipo cambio"}:
                rename_map[col] = "tipo_cambio"
            else:
                for source_name, target_name in FUEL_TARGETS.items():
                    if _norm_text(source_name) == norm:
                        rename_map[col] = target_name
                        break

        data = data.rename(columns=rename_map)

        required = {"fecha", "tipo_cambio", "Superior", "Regular", "Diésel", "Búnker", "GLP"}
        missing  = required - set(data.columns)
        if missing:
            LOGGER.warning("Hoja '%s' omitida: faltan columnas %s", sheet_name, sorted(missing))
            continue

        use = data[["fecha", "tipo_cambio", "Superior", "Regular", "Diésel", "Búnker", "GLP"]].copy()
        use["fecha"]       = pd.to_datetime(use["fecha"], errors="coerce")
        use["tipo_cambio"] = pd.to_numeric(use["tipo_cambio"], errors="coerce")
        use = use[use["fecha"].notna() & use["tipo_cambio"].notna() & (use["tipo_cambio"] != 0)].copy()

        for fuel in ["Superior", "Regular", "Diésel", "Búnker", "GLP"]:
            use[fuel] = pd.to_numeric(use[fuel], errors="coerce")

        long_df = use.melt(
            id_vars=["fecha", "tipo_cambio"],
            value_vars=["Superior", "Regular", "Diésel", "Búnker", "GLP"],
            var_name="combustible",
            value_name="precio",
        )
        long_df = long_df[long_df["precio"].notna()].copy()
        frames.append(long_df)

    if not frames:
        raise RuntimeError(
            "No se pudieron extraer datos válidos del Excel del MEM. "
            "La estructura del archivo puede haber cambiado."
        )

    out = pd.concat(frames, ignore_index=True)
    out["fecha"] = pd.to_datetime(out["fecha"]).dt.normalize()
    out = out.drop_duplicates(subset=["fecha", "combustible"]).sort_values(["fecha", "combustible"])
    return out[["fecha", "combustible", "precio", "tipo_cambio"]].reset_index(drop=True)

# ── Histórico existente ───────────────────────────────────────────────────────

def load_existing_csv(csv_path: str | Path = OUTPUT_CSV) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        LOGGER.info("CSV histórico no encontrado, se creará desde cero.")
        return pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])
    df = pd.read_csv(path)
    df["fecha"]       = pd.to_datetime(df["fecha"], errors="coerce")
    df["precio"]      = pd.to_numeric(df["precio"], errors="coerce")
    df["tipo_cambio"] = pd.to_numeric(df["tipo_cambio"], errors="coerce")
    return df[df["fecha"].notna()].copy()

# ── Merge con prioridad ───────────────────────────────────────────────────────

def merge_sources(
    existing: pd.DataFrame,
    api_df:   pd.DataFrame,
    excel_df: pd.DataFrame,
) -> pd.DataFrame:
    """Combina tres fuentes con la siguiente prioridad ante conflictos:

    Excel (2) > API (1) > Histórico existente (0)
    """
    def tag(df: pd.DataFrame, priority: int) -> pd.DataFrame:
        df = df.copy()
        df["_priority"] = priority
        return df

    combined = pd.concat(
        [tag(existing, 0), tag(api_df, 1), tag(excel_df, 2)],
        ignore_index=True,
    )
    combined["fecha"] = pd.to_datetime(combined["fecha"]).dt.normalize()

    combined = combined.sort_values("_priority", ascending=False)
    combined = combined.drop_duplicates(subset=["fecha", "combustible"], keep="first")
    combined = combined.drop(columns=["_priority"])

    return (
        combined
        .sort_values(["fecha", "combustible"])
        .reset_index(drop=True)
    )

# ── Guardar CSV ───────────────────────────────────────────────────────────────

def save_csv(df: pd.DataFrame, output_csv: str | Path = OUTPUT_CSV) -> Path:
    output_path = Path(output_csv)
    df_out = df.copy()
    df_out["fecha"] = pd.to_datetime(df_out["fecha"]).dt.strftime("%Y-%m-%d")
    df_out.to_csv(output_path, index=False, encoding="utf-8")
    return output_path

# ── Orquestador principal ─────────────────────────────────────────────────────

def _build_session() -> requests.Session:
    """Crea una sesión HTTP que imita un navegador real, con reintentos automáticos."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "es-GT,es;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    })
    retry = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def run(output_csv: str | Path = OUTPUT_CSV) -> tuple[pd.DataFrame, str]:
    """Actualiza el CSV histórico combinando API y Excel del MEM."""
    session = _build_session()

    # Warm-up: visita la página principal para obtener cookies de sesión
    try:
        _get_mem("https://mem.gob.gt/", session, timeout=15)
        time.sleep(1)
    except Exception:
        pass

    # 1. Histórico existente
    existing = load_existing_csv(output_csv)
    LOGGER.info("Histórico existente: %s filas", len(existing))

    # 2. Fuente API (no interrumpe el flujo si falla)
    api_df = fetch_api_rows(session)

    # 3. Fuente Excel con fallback a URL cacheada
    excel_df  = pd.DataFrame(columns=["fecha", "combustible", "precio", "tipo_cambio"])
    excel_url = "(no descargado)"

    try:
        excel_url   = find_excel_url(session)
        excel_bytes = download_excel_bytes(excel_url, session)
        excel_df    = parse_workbook(excel_bytes)
        LOGGER.info("Excel MEM: %s filas extraídas", len(excel_df))

    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        LOGGER.warning("Error HTTP %s al descargar Excel del MEM.", status)

        cached_url = _load_cached_excel_url()
        if cached_url and cached_url != excel_url:
            LOGGER.info("Reintentando con URL cacheada: %s", cached_url)
            try:
                excel_bytes = download_excel_bytes(cached_url, session)
                excel_df    = parse_workbook(excel_bytes)
                excel_url   = cached_url
                LOGGER.info("Fallback exitoso: %s filas del Excel cacheado", len(excel_df))
            except Exception as exc2:
                LOGGER.warning("Fallback de URL cacheada también falló: %s", exc2)
        else:
            LOGGER.warning(
                "Sin URL cacheada disponible. "
                "Se actualizará solo con API + histórico existente."
            )

    except Exception as exc:
        LOGGER.warning("Error inesperado al procesar Excel: %s", exc)

    # 4. Merge con prioridad Excel > API > Histórico (siempre se ejecuta)
    final_df = merge_sources(existing, api_df, excel_df)

    # 5. Guardar
    save_csv(final_df, output_csv)

    nuevas = len(final_df) - len(existing)
    LOGGER.info(
        "CSV actualizado: %s filas totales (%s nuevas) | fuente Excel: %s",
        len(final_df), max(nuevas, 0), excel_url,
    )
    return final_df, excel_url


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    dataframe, source_url = run()
    print(f"OK | {len(dataframe)} filas | {source_url}")
