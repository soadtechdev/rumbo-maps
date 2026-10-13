#!/usr/bin/env python3
"""Recorta los mapas de Rumbo de la compilación diaria de Protomaps y escribe su catálogo.

    ./build.py 20261013

Deja en dist/ un fichero PMTiles por zona de regions.json y actualiza catalog.json, que es lo
que lee la app. Los ficheros se publican después como adjuntos de una Release con el mismo
nombre que la versión (2026.10.13). Necesita la herramienta `pmtiles`.
"""
import hashlib
import json
import pathlib
import subprocess
import sys

REPOSITORY = "soadtechdev/rumbo-maps"
ROOT = pathlib.Path(__file__).parent


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        })

    catalog = {"formatVersion": 1, "packages": packages}
    (ROOT / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    print(f"catalog.json actualizado: {len(packages)} paquete(s), versión {version}")


if __name__ == "__main__":
    main()
