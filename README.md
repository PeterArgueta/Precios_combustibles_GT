# Precios de combustibles en Guatemala

Proyecto de **recopilación, transformación y visualización de datos** sobre precios de combustibles en Guatemala. El objetivo es facilitar el seguimiento histórico de los valores publicados y su consulta mediante un tablero web.

**Visualización pública:** https://peterargueta.github.io/Precios_combustibles_GT/

## Flujo de procesamiento

```text
Fuente pública (MEM)
        ↓
scraper.py             Localización y descarga de datos
        ↓
precios_historicos.csv Serie histórica procesada
        ↓
build_dashboard.py     Generación de la visualización
        ↓
index.html             Tablero estático publicado
```

`update_prices.py` coordina la actualización y registra los errores del proceso. El repositorio también contiene `international_prices.py` y `precios_internacionales.csv` para el procesamiento de una serie adicional.

## Componentes principales

| Archivo | Función |
| --- | --- |
| `scraper.py` | Localiza la fuente de precios diarios del Ministerio de Energía y Minas, descarga el archivo Excel y transforma los registros históricos. |
| `update_prices.py` | Ejecuta la actualización y controla errores del proceso. |
| `build_dashboard.py` | Genera `index.html` a partir de los datos disponibles. |
| `international_prices.py` | Procesamiento de información de precios internacionales. |
| `precios_historicos.csv` | Serie histórica utilizada por el tablero. |
| `precios_internacionales.csv` | Conjunto complementario de precios internacionales. |

## Ejecución local

Se requiere Python y acceso a Internet para consultar la fuente externa.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python update_prices.py
```

Para regenerar únicamente la interfaz con datos ya disponibles:

```bash
python build_dashboard.py
```

Revisa los archivos CSV resultantes y abre `index.html` en un navegador para comprobar la visualización. El repositorio contiene flujos de GitHub Actions en `.github/` para tareas automatizadas.

## Criterios de interpretación

- La información depende de la disponibilidad y estructura de las fuentes originales.
- Los cambios en el formato de las hojas Excel pueden requerir ajustes al proceso de extracción.
- Las cifras publicadas deben contrastarse con la fuente oficial y la fecha de referencia antes de citarlas en informes.
- La presencia de un dato histórico no implica que corresponda al precio vigente.

## Calidad y mantenimiento

El procesamiento incluye scripts independientes para extracción, actualización y construcción del tablero. El seguimiento de errores se realiza mediante un archivo de registro local. 

Los CSV históricos se conservan deliberadamente como parte de los datos del proyecto. Los registros temporales, cachés y entornos virtuales **no** deberían incorporarse al control de versiones. 
## Fuente y atribución

Fuente principal: [Ministerio de Energía y Minas de Guatemala (MEM)](https://mem.gob.gt/). Este es un proyecto independiente de procesamiento y visualización; no constituye una publicación oficial del MEM.
