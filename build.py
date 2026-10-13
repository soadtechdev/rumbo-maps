#!/usr/bin/env python3
"""Genera los mapas de Rumbo y su catálogo.

    ./build.py region es-vc 20261013     Mapa y grafo de carreteras de una zona, en dist/.
    ./build.py catalog 20261013          Reúne en catalog.json lo generado para esa versión.
    ./build.py matrix [grupo]            Las zonas de regions.json, para la matriz de la tarea automática.

De cada zona salen dos ficheros: el mapa (teselas vectoriales PMTiles, recortadas de la compilación
diaria de Protomaps) y el grafo de carreteras para calcular rutas sin conexión (teselas de Valhalla
en un .tar, generadas del extracto de OpenStreetMap de la zona). Junto a ellos queda un .json con
lo que el catálogo dice del paquete. Los ficheros se publican como adjuntos de una Release con el
nombre de la versión (2026.10.13).

Necesita `pmtiles` y Docker.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

REPOSITORY = "soadtechdev/rumbo-maps"
# La misma versión de Valhalla que lleva la app: el grafo solo lo lee el motor que lo generó.
VALHALLA_IMAGE = "ghcr.io/valhalla/valhalla:3.9.1"
MAX_ZOOM = 14
ROOT = pathlib.Path(__file__).parent
DIST = ROOT / "dist"


def version_of(build):
    return f"{build[:4]}.{build[4:6]}.{build[6:]}"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regions():
    return json.loads((ROOT / "regions.json").read_text())


def boundary_of(region, work):
    """El contorno de la zona, que acompaña a su extracto como fichero .poly, pasado a GeoJSON.

    Devuelve dónde queda el GeoJSON y el rectángulo que lo contiene: oeste, sur, este y norte.
    """
    url = region["osm"].replace("-latest.osm.pbf", ".poly").replace("/extracts/", "/polygons/")
    text = subprocess.run(["curl", "-fsSL", "--retry", "3", url], check=True, capture_output=True, text=True).stdout
    # Tras el nombre, cada anillo es un título, sus puntos «longitud latitud» y END; los huecos empiezan por «!».
    polygons, ring, is_hole = [], None, False
    for line in text.splitlines()[1:]:
        words = line.split()
        if not words:
            continue
        if words[0] == "END":
            if ring is not None:
                if len(ring) >= 3 and not is_hole:
                    polygons.append([ring + [ring[0]]])
                ring = None
        elif ring is None:
            ring, is_hole = [], words[0].startswith("!")
        else:
            ring.append([float(words[0]), float(words[1])])
    if not polygons:
        sys.exit(f"Sin contorno en {url}")

    path = work / "boundary.geojson"
    path.write_text(json.dumps({"type": "MultiPolygon", "coordinates": polygons}))
    points = [point for polygon in polygons for point in polygon[0]]
    return path, [
        round(min(point[0] for point in points), 4), round(min(point[1] for point in points), 4),
        round(max(point[0] for point in points), 4), round(max(point[1] for point in points), 4),
    ]


def build_routing(work, target):
    """Genera el grafo de carreteras de la zona, solo para coche."""
    script = (
        "valhalla_build_config --mjolnir-tile-dir /work/tiles --mjolnir-tile-extract /work/valhalla_tiles.tar"
        " --mjolnir-include-pedestrian False --mjolnir-include-bicycle False --mjolnir-include-platforms False"
        " > /work/valhalla.json"
        " && valhalla_build_tiles -c /work/valhalla.json /work/region.osm.pbf"
        " && valhalla_build_extract -c /work/valhalla.json"
        " && chmod -R a+rwX /work"
    )
    subprocess.run(["docker", "run", "--rm", "-v", f"{work}:/work", VALHALLA_IMAGE, "bash", "-c", script], check=True)
    (work / "valhalla_tiles.tar").replace(target)


def published(version, path):
    return {
        "url": f"https://github.com/{REPOSITORY}/releases/download/{version}/{path.name}",
        "sizeBytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def build_region(region_id, build):
    region = next(region for region in regions() if region["id"] == region_id)
    version = version_of(build)
    DIST.mkdir(exist_ok=True)
    work = DIST / "work" / region_id
    work.mkdir(parents=True, exist_ok=True)

    extract = work / "region.osm.pbf"
    if not extract.exists():
        subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(extract), region["osm"]], check=True)
    boundary, bounds = boundary_of(region, work)

    tiles = DIST / f"{region_id}.pmtiles"
    if not tiles.exists():
        subprocess.run(
            [
                "pmtiles", "extract", f"https://build.protomaps.com/{build}.pmtiles", str(tiles),
                f"--region={boundary}", f"--maxzoom={MAX_ZOOM}",
            ],
            check=True,
        )
    routing = DIST / f"{region_id}.valhalla.tar"
    if not routing.exists():
        build_routing(work, routing)

    package = {
        "id": region["id"],
        "code": region["code"],
        "country": region.get("country"),
        "name": region["name"],
        "summary": region["summary"],
        "bounds": bounds,
        "version": version,
        "dataDate": f"{build[:4]}-{build[4:6]}-{build[6:]}",
        **published(version, tiles),
        "routing": published(version, routing),
    }
    (DIST / f"{region_id}.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
    print(f"{region['name']}: mapa {tiles.stat().st_size >> 20} MB, rutas {routing.stat().st_size >> 20} MB")


def build_catalog(build, fragments):
    """Actualiza el catálogo con los paquetes recién generados; los demás se quedan como estaban."""
    path = ROOT / "catalog.json"
    packages = {package["id"]: package for package in json.loads(path.read_text())["packages"]} if path.exists() else {}
    for fragment in sorted(pathlib.Path(fragments).glob("*.json")):
        package = json.loads(fragment.read_text())
        packages[package["id"]] = package
    order = [region["id"] for region in regions()]
    listed = sorted(packages.values(), key=lambda package: order.index(package["id"]) if package["id"] in order else len(order))
    path.write_text(json.dumps({"formatVersion": 1, "packages": listed}, ensure_ascii=False, indent=2) + "\n")
    print(f"catalog.json: {len(listed)} paquete(s)")


def main():
    arguments = sys.argv[1:]
    if len(arguments) == 3 and arguments[0] == "region":
        build_region(arguments[1], arguments[2])
    elif len(arguments) in (2, 3) and arguments[0] == "catalog":
        build_catalog(arguments[1], arguments[2] if len(arguments) == 3 else DIST)
    elif arguments and arguments[0] == "matrix":
        group = arguments[1] if len(arguments) > 1 else ""
        print(json.dumps([region["id"] for region in regions() if not group or region.get("group") == group]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
