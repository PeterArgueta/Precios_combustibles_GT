# Precios de combustibles de Guatemala

Proyecto para descargar el histórico diario del MEM, limpiar filas inválidas y generar un dashboard interactivo autocontenido.

## Archivos
- `scraper.py`: localiza el enlace **Precios diarios** en el MEM, descarga el Excel y genera `precios_historicos.csv`.
- `build_dashboard.py`: genera `index.html` con datos embebidos.
- `update_prices.py`: orquesta el proceso y registra errores en `fuel_prices.log`.

## Uso local
```bash
pip install -r requirements.txt
python update_prices.py
```

## Publicación
Sube el contenido del repo a GitHub y publica `index.html` con GitHub Pages.
