from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)
OUTPUT_CSV = "precios_internacionales.csv"
START_DATE = pd.Timestamp("2026-01-01")

SERIES = {
    "Gasolina USGC": "https://www.eia.gov/dnav/pet/hist_xls/EER_EPMRU_PF4_RGC_DPGw.xls",
    "Diésel USGC": "https://www.eia.gov/dnav/pet/hist_xls/EER_EPD2DXL0_PF4_RGC_DPGw.xls",
}


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    })
    return session


def _extract_from_xls(content: bytes, benchmark: str) -> pd.DataFrame:
    """Extrae fecha y precio de los XLS históricos oficiales de EIA."""
    workbook = pd.read_excel(
        io.BytesIO(content),
        sheet_name=None,
        header=None,
        engine="xlrd",
    )

    candidates: list[pd.DataFrame] = []

    for sheet_name, raw in workbook.items():
        if raw.empty or raw.shape[1] < 2:
            continue

        # En los libros históricos de EIA la primera columna útil es la fecha.
        # Buscamos de forma tolerante por si cambian encabezados o filas introductorias.
        for date_col in range(min(3, raw.shape[1])):
            dates = pd.to_datetime(raw.iloc[:, date_col], errors="coerce")
            date_mask = dates.notna() & (dates >= START_DATE)
            if not date_mask.any():
                continue

            for value_col in range(date_col + 1, raw.shape[1]):
                values = pd.to_numeric(raw.iloc[:, value_col], errors="coerce")
                mask = date_mask & values.notna() & (values > 0)
                if mask.sum() < 2:
                    continue

                candidate = pd.DataFrame({
                    "fecha": dates[mask].dt.normalize(),
                    "benchmark": benchmark,
                    "precio_usd_gal": values[mask].astype(float),
                })
                candidates.append(candidate)

    if not candidates:
        raise RuntimeError(f"EIA XLS: no se extrajeron datos para {benchmark}")

    # Elegimos el bloque con más observaciones válidas; evita tomar hojas auxiliares.
    best = max(candidates, key=len)
    best = (
        best.drop_duplicates(["fecha", "benchmark"], keep="last")
        .sort_values("fecha")
        .reset_index(drop=True)
    )

    if best.empty:
        raise RuntimeError(f"EIA XLS: serie vacía para {benchmark}")

    return best


def fetch_series(
    session: requests.Session,
    benchmark: str,
    url: str,
) -> pd.DataFrame:
    LOGGER.info("Descargando referencia EIA XLS: %s", url)
    response = session.get(url, timeout=60)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    if "excel" not in content_type and len(response.content) < 1024:
        raise RuntimeError(
            f"EIA devolvió contenido inesperado ({content_type}, {len(response.content)} bytes)"
        )

    df = _extract_from_xls(response.content, benchmark)
    LOGGER.info(
        "EIA %s: %s observaciones, última=%s",
        benchmark,
        len(df),
        df["fecha"].max().strftime("%Y-%m-%d"),
    )
    return df


def run(output_csv: str | Path = OUTPUT_CSV) -> pd.DataFrame:
    output = Path(output_csv)
    frames: list[pd.DataFrame] = []
    session = _session()

    for benchmark, url in SERIES.items():
        try:
            frames.append(fetch_series(session, benchmark, url))
        except Exception as exc:
            LOGGER.warning("No se pudo actualizar %s desde EIA: %s", benchmark, exc)

    if not frames:
        if output.exists():
            LOGGER.warning(
                "EIA no disponible; se conserva precios_internacionales.csv existente."
            )
            return pd.read_csv(output, parse_dates=["fecha"])
        raise RuntimeError("No fue posible obtener referencias internacionales de EIA.")

    fresh = pd.concat(frames, ignore_index=True)

    if output.exists():
        old = pd.read_csv(output)
        old["fecha"] = pd.to_datetime(old["fecha"], errors="coerce")
        old["precio_usd_gal"] = pd.to_numeric(
            old["precio_usd_gal"], errors="coerce"
        )
        old = old[
            old["fecha"].notna()
            & old["precio_usd_gal"].notna()
            & (old["precio_usd_gal"] > 0)
        ]
        fresh = pd.concat([old, fresh], ignore_index=True)

    fresh["fecha"] = pd.to_datetime(fresh["fecha"]).dt.normalize()
    fresh = (
        fresh.drop_duplicates(["fecha", "benchmark"], keep="last")
        .sort_values(["benchmark", "fecha"])
        .reset_index(drop=True)
    )

    out = fresh.copy()
    out["fecha"] = out["fecha"].dt.strftime("%Y-%m-%d")
    out.to_csv(output, index=False)

    LOGGER.info(
        "Referencias internacionales actualizadas: %s filas (%s benchmarks)",
        len(out),
        out["benchmark"].nunique(),
    )
    return fresh


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    dataframe = run()
    print(f"OK | {len(dataframe)} observaciones internacionales")
