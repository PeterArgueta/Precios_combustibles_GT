# Precios de combustibles de Guatemala

ETL desde el MEM 

## Archivos
- `scraper.py`: localiza el enlace **Precios diarios** en el MEM, descarga el Excel y genera `precios_historicos.csv`.
- `build_dashboard.py`: genera `index.html` con datos embebidos.
- `update_prices.py`: orquesta el proceso y registra errores en `fuel_prices.log`.

## Uso local
```bash
pip install -r requirements.txt
python update_prices.py
```


