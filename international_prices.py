from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)
OUTPUT_CSV = "precios_internacionales.csv"
START_DATE = pd.Timestamp("2026-01-01")

SERIES = {
    "Gasolina USGC": "https://www.eia.gov/dnav/pet/hist/eer_epmru_pf4_rgc_dpgW.htm",
    "Diésel USGC": "https://www.eia.gov/dnav/pet/hist/EER_EPD2DXL0_PF4_RGC_DPGW.htm",
}

MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
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


def _parse_weekly_page(html: str, benchmark: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    records: list[dict] = []

    for tr in soup.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
        if not cells:
            continue

        head = re.fullmatch(r"(\d{4})-([A-Z][a-z]{2})", cells[0].strip())
        if not head:
            continue

        row_year = int(head.group(1))
        row_month = MONTHS.get(head.group(2))
        if row_month is None:
            continue

        i = 1
        while i + 1 < len(cells):
            date_text = cells[i].strip()
            value_text = cells[i + 1].strip().replace(",", "")
            dm = re.fullmatch(r"(\d{2})/(\d{2})", date_text)
            if dm:
                try:
                    value = float(value_text)
                except ValueError:
                    i += 2
                    continue

                month, day = map(int, dm.groups())
                year = row_year
                if row_month == 1 and month == 12:
                    year -= 1
                elif row_month == 12 and month == 1:
                    year += 1

                try:
                    date = pd.Timestamp(year=year, month=month, day=day)
                except ValueError:
                    i += 2
                    continue

                if date >= START_DATE and value > 0:
                    records.append({
                        "fecha": date,
                        "benchmark": benchmark,
                        "precio_usd_gal": value,
                    })
            i += 1

    if not records:
        raise RuntimeError(f"EIA: no se extrajeron datos para {benchmark}")

    return pd.DataFrame(records).drop_duplicates(["fecha", "benchmark"])


def fetch_series(session: requests.Session, benchmark: str, url: str) -> pd.DataFrame:
    LOGGER.info("Descargando referencia EIA: %s", url)
    response = session.get(url, timeout=60)
    response.raise_for_status()
    df = _parse_weekly_page(response.text, benchmark)
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
            LOGGER.warning("EIA no disponible; se conserva precios_internacionales.csv existente.")
            return pd.read_csv(output, parse_dates=["fecha"])
        raise RuntimeError("No fue posible obtener referencias internacionales de EIA.")

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
