from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)
OUTPUT_CSV = "precios_internacionales.csv"
START_YEAR = 2026

SERIES = {
    "Gasolina USGC": "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=M&n=PET&s=EER_EPMRU_PF4_RGC_DPG",
    "Diésel USGC": "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?f=M&n=PET&s=EER_EPD2DXL0_PF4_RGC_DPG",
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


def _parse_monthly_page(html: str, benchmark: str) -> pd.DataFrame:
    """Parsea la tabla mensual EIA: Year | Jan | ... | Dec."""
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict] = []

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) < 2:
            continue

        year_text = cells[0].replace("\xa0", " ").strip()
        if not year_text.isdigit():
            continue

        year = int(year_text)
        if year < START_YEAR:
            continue

        for month in range(1, min(13, len(cells))):
            value_text = cells[month].replace(",", "").strip()
            if value_text in {"", "-", "--", "NA", "W"}:
                continue
            try:
                value = float(value_text)
            except ValueError:
                continue
            if value <= 0:
                continue

            records.append({
                "fecha": pd.Timestamp(year=year, month=month, day=1),
                "benchmark": benchmark,
                "precio_usd_gal": value,
            })

    if not records:
        raise RuntimeError(f"EIA: no se extrajeron datos mensuales para {benchmark}")

    return pd.DataFrame(records).drop_duplicates(["fecha", "benchmark"])


def fetch_series(session: requests.Session, benchmark: str, url: str) -> pd.DataFrame:
    LOGGER.info("Descargando referencia mensual EIA: %s", url)
    response = session.get(url, timeout=60)
    response.raise_for_status()
    df = _parse_monthly_page(response.text, benchmark)
    LOGGER.info(
        "EIA %s: %s observaciones mensuales, última=%s",
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
            LOGGER.warning("EIA no disponible; se conserva precios_internacionales.csv existente.")
            return pd.read_csv(output, parse_dates=["fecha"])

        LOGGER.warning(
            "EIA no disponible y no existe caché internacional. "
            "Se continúa sin serie internacional para no interrumpir la actualización del MEM."
        )
        return pd.DataFrame(columns=["fecha", "benchmark", "precio_usd_gal"])

    fresh = pd.concat(frames, ignore_index=True)

    if output.exists():
        old = pd.read_csv(output)
        old["fecha"] = pd.to_datetime(old["fecha"], errors="coerce")
        old["precio_usd_gal"] = pd.to_numeric(old["precio_usd_gal"], errors="coerce")
        old = old[old["fecha"].notna() & old["precio_usd_gal"].notna()]
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
    return fresh


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    dataframe = run()
    print(f"OK | {len(dataframe)} observaciones internacionales")
