#!/usr/bin/env python3
"""Recorta los mapas de Rumbo de la compilación diaria de Protomaps y escribe su catálogo.

    ./build.py 20261013

Deja en dist/, por cada zona de regions.json, su mapa (PMTiles) y su grafo de carreteras para
calcular rutas (teselas de Valhalla en un .tar), y actualiza catalog.json, que es lo que lee la
app. Los ficheros se publican después como adjuntos de una Release con el mismo nombre que la
versión (2026.10.13). Necesita la herramienta `pmtiles` y Docker.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

REPOSITORY = "soadtechdev/rumbo-maps"
# La misma versión de Valhalla que lleva la app: el grafo solo lo lee el motor que lo generó.
VALHALLA_IMAGE = "ghcr.io/valhalla/valhalla:3.9.1"
ROOT = pathlib.Path(__file__).parent


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_routing(region, target):
    """Genera el grafo de carreteras de la zona, solo para coche, a partir de su extracto de OpenStreetMap."""
    work = target.parent / "work" / region["id"]
    work.mkdir(parents=True, exist_ok=True)
    extract = work / "region.osm.pbf"
    if not extract.exists():
        subprocess.run(["curl", "-fL", "-o", str(extract), region["osm"]], check=True)
    script = (
        "valhalla_build_config --mjolnir-tile-dir /work/tiles --mjolnir-tile-extract /work/valhalla_tiles.tar"
        " --mjolnir-include-pedestrian False --mjolnir-include-bicycle False --mjolnir-include-platforms False"
        " > /work/valhalla.json"
        " && valhalla_build_tiles -c /work/valhalla.json /work/region.osm.pbf"
        " && valhalla_build_extract -c /work/valhalla.json"
    )
    subprocess.run(["docker", "run", "--rm", "-v", f"{work}:/work", VALHALLA_IMAGE, "bash", "-c", script], check=True)
    (work / "valhalla_tiles.tar").replace(target)


def published(repository, version, path):
    return {
        "url": f"https://github.com/{repository}/releases/download/{version}/{path.name}",
        "sizeBytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def main():
    if len(sys.argv) != 2 or len(sys.argv[1]) != 8:
        sys.exit("Uso: ./build.py AAAAMMDD  (compilaciones en https://build-metadata.protomaps.dev/builds.json)")
    build = sys.argv[1]
    version = f"{build[:4]}.{build[4:6]}.{build[6:]}"
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)

    packages = []
    for region in json.loads((ROOT / "regions.json").read_text()):
        target = dist / region["file"]
        if not target.exists():
            subprocess.run(
                [
                    "pmtiles", "extract", f"https://build.protomaps.com/{build}.pmtiles", str(target),
                    "--bbox=" + ",".join(str(value) for value in region["bounds"]),
                    f"--maxzoom={region['maxZoom']}",
                ],
                check=True,
            )
        routing = dist / region["routingFile"]
        if not routing.exists():
            build_routing(region, routing)
        packages.append({
            "id": region["id"],
            "code": region["code"],
            "name": region["name"],
            "summary": region["summary"],
            "bounds": region["bounds"],
            "version": version,
            "dataDate": f"{build[:4]}-{build[4:6]}-{build[6:]}",
            "sizeBytes": target.stat().st_size,
            "sha256": sha256(target),
            "url": f"https://github.com/{REPOSITORY}/releases/download/{version}/{region['file']}",
            "routing": published(REPOSITORY, version, routing),
        })

    catalog = {"formatVersion": 1, "packages": packages}
    (ROOT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"catalog.json actualizado: {len(packages)} paquete(s), versión {version}")


if __name__ == "__main__":
    main()
