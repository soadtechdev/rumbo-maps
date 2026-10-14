#!/usr/bin/env python3
"""Genera los mapas de Rumbo y su catálogo.

    ./build.py map es-vc 20261013      El mapa de una zona, en dist/.
    ./build.py graph es 20261013       Una red de carreteras entera, repartida entre sus zonas.
    ./build.py addresses es 2026.10.13 Los portales de un país, repartidos entre sus zonas.
    ./build.py catalog [carpeta]       Reúne en catalog.json lo generado.
    ./build.py plan [grupo]            Zonas y redes de regions.json y graphs.json, para la tarea automática.

De cada zona salen dos ficheros. El mapa: teselas vectoriales PMTiles, recortadas por el contorno
de la zona de la compilación diaria de Protomaps. Y sus carreteras, para calcular rutas sin
conexión: las teselas de Valhalla que tocan la zona, en un .tar.

Las carreteras no se generan zona a zona. Se genera una sola red para todo un país (graphs.json) y
después se reparte: así las teselas de dos zonas encajan entre sí y una ruta puede cruzar de una a
otra. Las teselas de redes distintas no se pueden mezclar; por eso cada paquete dice de qué red
salió («es-2026.10.13»).

Del mismo extracto de OpenStreetMap salen las direcciones: cada portal con número, agrupado por
calle y municipio (el de sus límites administrativos, no el pueblo más cercano), para buscar
«Calle de la Rioja, 73, Leganés» sin conexión. El mapa de Protomaps no trae portales.

Los ficheros se publican como adjuntos de una Release con el nombre de la versión (2026.10.13).
Necesita `pmtiles` y Docker; las direcciones, los módulos de Python `osmium` y `shapely`.
"""
import hashlib
import json
import math
import pathlib
import re
import subprocess
import sys
import tarfile

REPOSITORY = "soadtechdev/rumbo-maps"
# La misma versión de Valhalla que lleva la app: el grafo solo lo lee el motor que lo generó.
VALHALLA_IMAGE = "ghcr.io/valhalla/valhalla:3.9.1"
MAX_ZOOM = 14
# Lado, en grados, de las teselas de Valhalla de cada nivel: autovías, carreteras y calles.
TILE_SIZES = {0: 4.0, 1: 1.0, 2: 0.25}
# Margen, en grados, con el que una tesela cuenta como parte de una zona.
TILE_MARGIN = 0.02
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


def graphs():
    return json.loads((ROOT / "graphs.json").read_text())


def published(version, path):
    return {
        "url": f"https://github.com/{REPOSITORY}/releases/download/{version}/{path.name}",
        "sizeBytes": path.stat().st_size,
        "sha256": sha256(path),
    }


# Contornos

def rings_of(region):
    """Los anillos exteriores del contorno de la zona, que acompaña a su extracto como fichero .poly."""
    url = region["osm"].replace("-latest.osm.pbf", ".poly").replace("/extracts/", "/polygons/")
    text = subprocess.run(["curl", "-fsSL", "--retry", "3", url], check=True, capture_output=True, text=True).stdout
    # Tras el nombre, cada anillo es un título, sus puntos «longitud latitud» y END; los huecos empiezan por «!».
    rings, ring, is_hole = [], None, False
    for line in text.splitlines()[1:]:
        words = line.split()
        if not words:
            continue
        if words[0] == "END":
            if ring is not None:
                if len(ring) >= 3 and not is_hole:
                    rings.append(ring + [ring[0]])
                ring = None
        elif ring is None:
            ring, is_hole = [], words[0].startswith("!")
        else:
            ring.append((float(words[0]), float(words[1])))
    if not rings:
        sys.exit(f"Sin contorno en {url}")
    return rings


def bounds_of(rings):
    """Oeste, sur, este y norte del contorno."""
    points = [point for ring in rings for point in ring]
    return [
        round(min(point[0] for point in points), 4), round(min(point[1] for point in points), 4),
        round(max(point[0] for point in points), 4), round(max(point[1] for point in points), 4),
    ]


def contains(ring, x, y):
    """Si el punto cae dentro del anillo."""
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def border_points(rings, step=0.02):
    """El contorno recorrido a pasos cortos, para no saltarse ninguna tesela que cruce."""
    points = []
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            count = max(1, int(max(abs(x2 - x1), abs(y2 - y1)) / step))
            points += [(x1 + (x2 - x1) * index / count, y1 + (y2 - y1) * index / count) for index in range(count)]
    return points


def outline_of(rings, tolerance=0.01):
    """El contorno simplificado (a un kilómetro, más o menos) para que el iPhone sepa qué puntos
    cubre el mapa sin cargar el contorno entero: anillos de [longitud, latitud] con tres decimales."""
    def simplify(points):
        # Douglas-Peucker: se queda con el punto más alejado de la recta entre los extremos.
        if len(points) < 3:
            return points
        (x1, y1), (x2, y2) = points[0], points[-1]
        length = math.hypot(x2 - x1, y2 - y1)
        def distance(point):
            if length == 0:
                return math.hypot(point[0] - x1, point[1] - y1)
            return abs((x2 - x1) * (y1 - point[1]) - (x1 - point[0]) * (y2 - y1)) / length
        index, farthest = max(((i, distance(point)) for i, point in enumerate(points[1:-1], 1)), key=lambda item: item[1])
        if farthest <= tolerance:
            return [points[0], points[-1]]
        return simplify(points[:index + 1])[:-1] + simplify(points[index:])

    outline = []
    for ring in rings:
        # El anillo cerrado se parte en dos mitades para que sus extremos no coincidan.
        middle = len(ring) // 2
        simple = simplify(ring[:middle + 1])[:-1] + simplify(ring[middle:])
        if len(simple) >= 4:
            outline.append([[round(x, 3), round(y, 3)] for x, y in simple])
    return outline


# Mapas

def build_map(region_id, build):
    region = next(region for region in regions() if region["id"] == region_id)
    version = version_of(build)
    DIST.mkdir(exist_ok=True)
    rings = rings_of(region)
    boundary = DIST / f"{region_id}.boundary.geojson"
    boundary.write_text(json.dumps({"type": "MultiPolygon", "coordinates": [[ring] for ring in rings]}))

    tiles = DIST / f"{region_id}.pmtiles"
    if not tiles.exists():
        subprocess.run(
            [
                "pmtiles", "extract", f"https://build.protomaps.com/{build}.pmtiles", str(tiles),
                f"--region={boundary}", f"--maxzoom={MAX_ZOOM}",
            ],
            check=True,
        )
    package = {
        "id": region["id"],
        "code": region["code"],
        "country": region.get("country"),
        "name": region["name"],
        "summary": region["summary"],
        "bounds": bounds_of(rings),
        "outline": outline_of(rings),
        "version": version,
        "dataDate": f"{build[:4]}-{build[4:6]}-{build[6:]}",
        **published(version, tiles),
    }
    (DIST / f"{region_id}.map.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n")
    print(f"{region['name']}: mapa de {tiles.stat().st_size >> 20} MB")


# Carreteras

def build_graph(graph_id, build):
    version = version_of(build)
    work = DIST / "work" / graph_id
    country_extract(graph_id)

    tiles = work / "tiles"
    if not tiles.exists():
        # Solo para coche: sin sendas, carriles bici ni andenes el grafo pesa un tercio menos.
        script = (
            "valhalla_build_config --mjolnir-tile-dir /work/tiles"
            " --mjolnir-include-pedestrian False --mjolnir-include-bicycle False --mjolnir-include-platforms False"
            " > /work/valhalla.json"
            " && valhalla_build_tiles -c /work/valhalla.json /work/region.osm.pbf"
            " && chmod -R a+rwX /work"
        )
        subprocess.run(["docker", "run", "--rm", "-v", f"{work}:/work", VALHALLA_IMAGE, "bash", "-c", script], check=True)

    # Cada tesela, con el rectángulo que ocupa: su nombre es su número en la cuadrícula de su nivel.
    cells = []
    for path in sorted(tiles.glob("[012]/**/*.gph")):
        relative = path.relative_to(tiles)
        level = int(relative.parts[0])
        number = int("".join(relative.parts[1:]).removesuffix(".gph"))
        size = TILE_SIZES[level]
        columns = int(360 / size)
        west, south = (number % columns) * size - 180, (number // columns) * size - 90
        cells.append((path, relative, west, south, west + size, south + size))

    for region in regions():
        if region.get("graph") != graph_id:
            continue
        rings = rings_of(region)
        border = border_points(rings)

        def touches(cell):
            _, _, west, south, east, north = cell
            if any(west - TILE_MARGIN <= x <= east + TILE_MARGIN and south - TILE_MARGIN <= y <= north + TILE_MARGIN for x, y in border):
                return True
            # Una tesela entera dentro de la zona no toca su contorno.
            return any(contains(ring, (west + east) / 2, (south + north) / 2) for ring in rings)

        target = DIST / f"{region['id']}.valhalla.tar"
        owned = [cell for cell in cells if touches(cell)]
        with tarfile.open(target, "w", format=tarfile.USTAR_FORMAT) as archive:
            for path, relative, *_ in owned:
                archive.add(path, arcname=str(relative))
        routing = {**published(version, target), "graph": f"{graph_id}-{version}"}
        (DIST / f"{region['id']}.routing.json").write_text(json.dumps(routing, indent=2) + "\n")
        print(f"{region['name']}: {len(owned)} teselas de carreteras, {target.stat().st_size >> 20} MB")


# Direcciones

def country_extract(graph_id):
    """El extracto de OpenStreetMap de una red, descargado una sola vez."""
    work = DIST / "work" / graph_id
    work.mkdir(parents=True, exist_ok=True)
    extract = work / "region.osm.pbf"
    if not extract.exists():
        subprocess.run(["curl", "-fL", "--retry", "3", "-o", str(extract), graphs()[graph_id]["osm"]], check=True)
    return extract


def build_addresses(graph_id, version):
    """Los portales con número del país de una red, repartidos entre sus zonas.

    Cada zona recibe un .addresses.json.gz con sus calles: el nombre en castellano (el de la vía
    con ese nombre más cercana, si lo tiene), el original si es otro, el municipio y sus portales
    con sus coordenadas en cienmilésimas de grado.
    """
    import gzip
    import osmium
    import shapely
    from shapely import wkb
    from shapely.strtree import STRtree

    factory = osmium.geom.WKBFactory()

    class Reader(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.municipalities = []
            self.ways = {}
            self.addresses = []

        def node(self, node):
            tags = node.tags
            if "addr:housenumber" in tags and "addr:street" in tags and node.location.valid():
                self.addresses.append((tags["addr:street"], tags["addr:housenumber"], node.location.lat, node.location.lon, tags.get("addr:city")))

        def way(self, way):
            tags = way.tags
            if "highway" in tags and "name" in tags:
                middle = way.nodes[len(way.nodes) // 2]
                if middle.location.valid():
                    self.ways.setdefault(tags["name"], []).append((tags.get("name:es") or tags["name"], middle.location.lat, middle.location.lon))
            if "addr:housenumber" in tags and "addr:street" in tags:
                points = [(node.location.lat, node.location.lon) for node in way.nodes if node.location.valid()]
                if points:
                    latitude = sum(point[0] for point in points) / len(points)
                    longitude = sum(point[1] for point in points) / len(points)
                    self.addresses.append((tags["addr:street"], tags["addr:housenumber"], latitude, longitude, tags.get("addr:city")))

        def area(self, area):
            tags = area.tags
            if tags.get("boundary") == "administrative" and tags.get("admin_level") == "8" and "name" in tags:
                try:
                    self.municipalities.append((wkb.loads(factory.create_multipolygon(area), hex=True), tags.get("name:es") or tags["name"]))
                except Exception:
                    pass

    reader = Reader()
    reader.apply_file(str(country_extract(graph_id)), locations=True)
    print(f"{graph_id}: {len(reader.addresses)} portales, {len(reader.municipalities)} municipios")

    def spanish_name(street, latitude, longitude):
        best, best_distance = street, 1.5
        for spanish, way_latitude, way_longitude in reader.ways.get(street, ()):
            distance = math.hypot((way_latitude - latitude) * 111, (way_longitude - longitude) * 111 * math.cos(math.radians(latitude)))
            if distance < best_distance:
                best, best_distance = spanish, distance
        return best

    points = shapely.points([address[3] for address in reader.addresses], [address[2] for address in reader.addresses])
    municipality = [None] * len(points)
    tree = STRtree([polygon for polygon, _ in reader.municipalities])
    for point, found in zip(*tree.query(points, predicate="within")):
        municipality[point] = reader.municipalities[found][1]

    zones = [region for region in regions() if region.get("graph") == graph_id]
    shapes = [shapely.MultiPolygon([shapely.Polygon(ring) for ring in rings_of(region)]) for region in zones]
    groups = [dict() for _ in zones]
    zone_tree = STRtree(shapes)
    for point, zone in zip(*zone_tree.query(points, predicate="within")):
        street, number, latitude, longitude, city = reader.addresses[point]
        town = municipality[point] or city
        if not town:
            continue
        spanish = spanish_name(street, latitude, longitude)
        key = (spanish, "" if street == spanish else street, town)
        groups[zone].setdefault(key, []).append((number.strip(), round(latitude * 1e5), round(longitude * 1e5)))

    for region, group in zip(zones, groups):
        streets = []
        for (spanish, native, town), numbers in sorted(group.items()):
            numbers.sort(key=lambda number: (len(number[0]), number[0]))
            streets.append([spanish, native, town, [n[0] for n in numbers], [n[1] for n in numbers], [n[2] for n in numbers]])
        target = DIST / f"{region['id']}.addresses.json.gz"
        with gzip.open(target, "wb", compresslevel=9) as file:
            file.write(json.dumps({"format": 1, "streets": streets}, ensure_ascii=False, separators=(",", ":")).encode())
        (DIST / f"{region['id']}.addresses.json").write_text(json.dumps(published(version, target), indent=2) + "\n")
        print(f"{region['name']}: {sum(len(street[3]) for street in streets)} portales en {len(streets)} calles, {target.stat().st_size >> 10} KB")


# Catálogo

def build_catalog(fragments):
    """Actualiza el catálogo con los paquetes recién generados; los demás se quedan como estaban.

    Un paquete entra cuando tiene su mapa; sus carreteras se añaden si también salieron.
    """
    fragments = pathlib.Path(fragments)
    path = ROOT / "catalog.json"
    packages = {package["id"]: package for package in json.loads(path.read_text())["packages"]} if path.exists() else {}
    for fragment in sorted(fragments.glob("*.map.json")):
        package = json.loads(fragment.read_text())
        routing = fragments / fragment.name.replace(".map.json", ".routing.json")
        if routing.exists():
            package["routing"] = json.loads(routing.read_text())
        packages[package["id"]] = package
    # Las direcciones pueden generarse solas, sin rehacer el mapa: se añaden al paquete que haya.
    for fragment in sorted(fragments.glob("*.addresses.json")):
        region_id = fragment.name.removesuffix(".addresses.json")
        if region_id in packages:
            packages[region_id]["addresses"] = json.loads(fragment.read_text())
    # Nombres y descripciones salen siempre de regions.json: corregirlos no obliga a generar de nuevo.
    # El contorno de los paquetes que aún no lo traen se añade aquí, por la misma razón.
    for region in regions():
        if region["id"] in packages:
            package = packages[region["id"]]
            package.update(name=region["name"], summary=region["summary"])
            if "outline" not in package:
                package["outline"] = outline_of(rings_of(region))
    order = [region["id"] for region in regions()]
    listed = sorted(packages.values(), key=lambda package: order.index(package["id"]) if package["id"] in order else len(order))
    text = json.dumps({"formatVersion": 1, "packages": listed}, ensure_ascii=False, indent=2)
    # Cada punto de un contorno, en una línea: con un número por línea el fichero se multiplica.
    text = re.sub(r"\[\s+(-?[\d.]+),\s+(-?[\d.]+)\s+\]", r"[\1, \2]", text)
    path.write_text(text + "\n")
    print(f"catalog.json: {len(listed)} paquete(s)")


def main():
    arguments = sys.argv[1:]
    if len(arguments) == 3 and arguments[0] == "map":
        build_map(arguments[1], arguments[2])
    elif len(arguments) == 3 and arguments[0] == "graph":
        build_graph(arguments[1], arguments[2])
    elif len(arguments) == 3 and arguments[0] == "addresses":
        build_addresses(arguments[1], arguments[2])
    elif arguments and arguments[0] == "catalog":
        build_catalog(arguments[1] if len(arguments) > 1 else DIST)
    elif arguments and arguments[0] == "plan":
        group = arguments[1] if len(arguments) > 1 else ""
        print(json.dumps({
            "regions": [region["id"] for region in regions() if not group or region.get("group") == group],
            "graphs": [graph for graph, details in graphs().items() if not group or details.get("group") == group],
        }))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
