
from __future__ import annotations

import logging
from pathlib import Path

import build_dashboard
import scraper

LOG_FILE = "fuel_prices.log"

def main() -> int:
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    logging.getLogger("").addHandler(console)

    try:
        df, source_url = scraper.run("precios_historicos.csv")
        build_dashboard.main("precios_historicos.csv", "index.html")
        logging.info("Actualización completada. Filas: %s | Fuente: %s", len(df), source_url)
        return 0
    except Exception as exc:
        logging.exception("Falló la actualización diaria: %s", exc)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
