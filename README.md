# Rumbo · mapas

Mapas sin conexión de Rumbo, la app de navegación para volver a casa cuando no hay cobertura.

- `catalog.json`: lo que la app ofrece para descargar. Cada paquete indica su zona, su tamaño, la fecha de sus datos y dónde está el fichero.
- Los ficheros se publican como adjuntos de cada [Release](../../releases): el mapa (`.pmtiles`, teselas vectoriales) y su grafo de carreteras para calcular rutas sin conexión (`.valhalla.tar`, teselas de [Valhalla](https://github.com/valhalla/valhalla) 3.9.1).
- `regions.json`: las zonas que se generan, cada una con su extracto de OpenStreetMap.
- `build.py`: recorta los mapas de la compilación diaria de [Protomaps](https://protomaps.com), genera los grafos de carreteras con Docker y reúne el catálogo.
- `.github/workflows/build.yml`: la tarea automática que lo ejecuta y publica.

## Publicar una versión

Lo hace sola la tarea **Generar mapas** (Actions), el día 2 de cada mes: genera cada zona, sube sus ficheros a una Release con el nombre de la versión y actualiza `catalog.json`. También se lanza a mano:

```sh
gh workflow run build.yml                 # todas las zonas, con la última compilación
gh workflow run build.yml -f group=es     # solo un grupo de zonas
```

Para probar una zona en local (con `pmtiles` y Docker):

```sh
./build.py region es-vc 20261013
```

## Licencia de los datos

© Colaboradores de [OpenStreetMap](https://www.openstreetmap.org/copyright), bajo la licencia ODbL. Teselas generadas con el esquema de mapa base de Protomaps.
