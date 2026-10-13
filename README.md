# Rumbo · mapas

Mapas sin conexión de Rumbo, la app de navegación para volver a casa cuando no hay cobertura.

- `catalog.json`: lo que la app ofrece para descargar. Cada paquete indica su zona, su tamaño, la fecha de sus datos y dónde está el fichero.
- Los ficheros (`.pmtiles`, teselas vectoriales) se publican como adjuntos de cada [Release](../../releases).
- `regions.json`: las zonas que se recortan.
- `build.py`: recorta las zonas de la compilación diaria de [Protomaps](https://protomaps.com) y reescribe el catálogo.

## Publicar una versión

```sh
brew install pmtiles
./build.py 20261013
git commit -am "Datos del 13 oct 2026" && git push
gh release create 2026.10.13 dist/*.pmtiles --title "2026.10.13" --notes "Datos de OpenStreetMap del 13 oct 2026."
```

## Licencia de los datos

© Colaboradores de [OpenStreetMap](https://www.openstreetmap.org/copyright), bajo la licencia ODbL. Teselas generadas con el esquema de mapa base de Protomaps.
