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

Necesita `pmtiles`, `osmium` y Docker.
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
# Margen alrededor de la zona, en grados, para que el mapa no acabe justo en la frontera.
MARGIN = 0.05
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


def bounds_of(extract):
    """Oeste, sur, este y norte de lo que contiene el extracto de OpenStreetMap."""
    info = json.loads(subprocess.run(
        ["osmium", "fileinfo", "--extended", "--json", str(extract)], check=True, capture_output=True, text=True
    ).stdout)
    west, south, east, north = info["data"]["bbox"]
    return [round(west - MARGIN, 4), round(south - MARGIN, 4), round(east + MARGIN, 4), round(north + MARGIN, 4)]


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
    bounds = region.get("bounds") or bounds_of(extract)

    tiles = DIST / f"{region_id}.pmtiles"
    if not tiles.exists():
        subprocess.run(
            [
                "pmtiles", "extract", f"https://build.protomaps.com/{build}.pmtiles", str(tiles),
                "--bbox=" + ",".join(str(value) for value in bounds), f"--maxzoom={MAX_ZOOM}",
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
