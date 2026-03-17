from __future__ import annotations

import io
import logging
import re
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

MEM_URL = "https://mem.gob.gt/que-hacemos/hidrocarburos/comercializacion-downstream/precios-combustible-nacionales/"
OUTPUT_CSV = "precios_historicos.csv"

LOGGER = logging.getLogger(__name__)

FUEL_TARGETS = {
    "Gasolina Superior": "Superior",
    "Gasolina Regular": "Regular",
    "ACEITE COMBUSTIBLE DIÉSEL": "Diésel",
    "ACEITE COMBUSTIBLE DIESEL": "Diésel",
    "Bunker": "Búnker",
    "Búnker": "Búnker",
    "GLP": "GLP",
}


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _norm_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    text = _strip_accents(text).lower()
    text = re.sub(r"\s+", " ", text)
    return text


def find_daily_prices_download_url(session: requests.Session | None = None) -> str:
    """Busca el enlace del MEM cuyo texto visible contenga
    'Precios diarios de combustibles' y usa su href directamente.
    """
    session = session or requests.Session()
    response = session.get(MEM_URL, timeout=60)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    matches: list[tuple[int, str, str]] = []

    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href", "")).strip()
        text = anchor.get_text(" ", strip=True)
        if not href or not text:
            continue

        href_lower = href.lower()
        if not (href_lower.endswith(".xlsx") or href_lower.endswith(".xls")):
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
            matches.append((score, text, urljoin(MEM_URL, href)))

    if not matches:
        raise RuntimeError(
            "No se encontró en la página del MEM un enlace Excel cuyo texto contenga "
            "'Precios diarios de combustibles'. Se detuvo la ejecución sin construir URLs manualmente."
        )

    matches.sort(key=lambda x: x[0], reverse=True)
    best = matches[0]
    LOGGER.info("Enlace del MEM detectado: texto='%s' | href=%s", best[1], best[2])
    return best[2]



def download_excel_bytes(url: str, session: requests.Session | None = None) -> bytes:
    session = session or requests.Session()
    response = session.get(url, timeout=120)
    response.raise_for_status()
    return response.content



def _find_header_row(raw: pd.DataFrame) -> int:
    """Detecta la fila que contiene FECHA y Tipo de Cambio.

    El archivo diario del MEM actual usa esa cabecera en la fila 7 (índice 6),
    pero esto se detecta dinámicamente para volverlo más robusto.
    """
    for idx in range(min(len(raw), 40)):
        row = [_norm_text(v) for v in raw.iloc[idx].tolist()]
        if "fecha" in row and ("tipo de cambio" in row or "tipo cambio" in row):
            return idx
    raise RuntimeError(
        "No se encontró la fila de encabezados del Excel del MEM. "
        "No aparece una fila con 'FECHA' y 'Tipo de Cambio'."
    )



def parse_workbook(excel_bytes: bytes) -> pd.DataFrame:
    workbook = pd.ExcelFile(io.BytesIO(excel_bytes))
    frames: list[pd.DataFrame] = []

    for sheet_name in workbook.sheet_names:
        raw = pd.read_excel(workbook, sheet_name=sheet_name, header=None)
        if raw.empty:
            continue

        header_row = _find_header_row(raw)
        header_values = raw.iloc[header_row].tolist()
        columns = []
        for i, value in enumerate(header_values):
            if value is None or pd.isna(value):
                columns.append(f"unnamed_{i}")
            else:
                columns.append(str(value).strip())

        data = raw.iloc[header_row + 2 :].copy()  # salta la fila de unidades
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
        missing = required - set(data.columns)
        if missing:
            LOGGER.warning("Hoja '%s' omitida: faltan columnas %s", sheet_name, sorted(missing))
            continue

        use = data[["fecha", "tipo_cambio", "Superior", "Regular", "Diésel", "Búnker", "GLP"]].copy()
        use["fecha"] = pd.to_datetime(use["fecha"], errors="coerce")
        use["tipo_cambio"] = pd.to_numeric(use["tipo_cambio"], errors="coerce")

        # Excluir filas inválidas de fin de semana: tipo de cambio 0 o vacío
        use = use[use["fecha"].notna()].copy()
        use = use[use["tipo_cambio"].notna() & (use["tipo_cambio"] != 0)].copy()

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
            "La estructura del archivo cambió o no contiene la tabla esperada."
        )

    out = pd.concat(frames, ignore_index=True)
    out["fecha"] = pd.to_datetime(out["fecha"]).dt.normalize()
    out = out.drop_duplicates(subset=["fecha", "combustible"]).sort_values(["fecha", "combustible"])
    return out[["fecha", "combustible", "precio", "tipo_cambio"]].reset_index(drop=True)



def save_csv(df: pd.DataFrame, output_csv: str | Path = OUTPUT_CSV) -> Path:
    output_path = Path(output_csv)
    df_to_save = df.copy()
    df_to_save["fecha"] = pd.to_datetime(df_to_save["fecha"]).dt.strftime("%Y-%m-%d")
    df_to_save.to_csv(output_path, index=False, encoding="utf-8")
    return output_path



def run(output_csv: str | Path = OUTPUT_CSV) -> tuple[pd.DataFrame, str]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        }
    )
    download_url = find_daily_prices_download_url(session=session)
    excel_bytes = download_excel_bytes(download_url, session=session)
    df = parse_workbook(excel_bytes)
    save_csv(df, output_csv=output_csv)
    LOGGER.info("CSV histórico actualizado con %s filas desde %s", len(df), download_url)
    return df, download_url


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    dataframe, source_url = run()
    print(f"OK | {len(dataframe)} filas | {source_url}")
