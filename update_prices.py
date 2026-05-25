from __future__ import annotations
import logging
from pathlib import Path
import requests
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
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 403:
            logging.warning(
                "El sitio del MEM bloqueó el acceso (403 Forbidden). "
                "Es probable que estén bloqueando IPs de servidores CI/CD temporalmente. "
                "Se omite la actualización de hoy sin marcar el workflow como fallido."
            )
            return 0
        logging.exception("Error HTTP inesperado (%s): %s", status, exc)
        return 1
    except Exception as exc:
        logging.exception("Falló la actualización diaria: %s", exc)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
