#!/usr/bin/env python3
"""Añade a regions.json las zonas de Europa, a partir del índice de extractos de Geofabrik.

    ./europe.py

Cada país entra entero, salvo los que Geofabrik reparte en regiones (Francia, Alemania, Italia…),
que entran región a región para que ningún fichero pase de los 2 GB que admite una Release.
España no se toca: sus comunidades están escritas a mano, con sus nombres en español.
"""
import json
import pathlib
import urllib.request

INDEX = "https://download.geofabrik.de/index-v1-nogeom.json"
ROOT = pathlib.Path(__file__).parent
# Agrupaciones que repiten lo que ya cubren sus países, y territorios fuera de Europa.
SKIPPED = {"spain", "alps", "dach", "britain-and-ireland", "great-britain", "bermuda", "falklands", "svalbard-janmayen"}
# Nombre en español de cada país, por su identificador en Geofabrik.
COUNTRIES = {
    "albania": "Albania", "andorra": "Andorra", "austria": "Austria", "azores": "Azores", "belarus": "Bielorrusia",
    "belgium": "Bélgica", "bosnia-herzegovina": "Bosnia y Herzegovina", "bulgaria": "Bulgaria", "croatia": "Croacia",
    "cyprus": "Chipre", "czech-republic": "Chequia", "denmark": "Dinamarca", "estonia": "Estonia",
    "faroe-islands": "Islas Feroe", "finland": "Finlandia", "france": "Francia", "georgia": "Georgia",
    "germany": "Alemania", "greece": "Grecia", "guernsey-jersey": "Guernsey y Jersey", "hungary": "Hungría",
    "iceland": "Islandia", "ireland-and-northern-ireland": "Irlanda e Irlanda del Norte", "isle-of-man": "Isla de Man",
    "italy": "Italia", "kosovo": "Kosovo", "latvia": "Letonia", "liechtenstein": "Liechtenstein", "lithuania": "Lituania",
    "luxembourg": "Luxemburgo", "macedonia": "Macedonia del Norte", "malta": "Malta", "moldova": "Moldavia",
    "monaco": "Mónaco", "montenegro": "Montenegro", "netherlands": "Países Bajos", "norway": "Noruega",
    "poland": "Polonia", "portugal": "Portugal", "romania": "Rumanía", "serbia": "Serbia", "slovakia": "Eslovaquia",
    "slovenia": "Eslovenia", "sweden": "Suecia", "switzerland": "Suiza", "turkey": "Turquía", "ukraine": "Ucrania",
    "united-kingdom": "Reino Unido",
}


# Códigos de los territorios que el índice deja sin código de país.
CODES = {"kosovo": "XK", "isle-of-man": "IM", "guernsey-jersey": "GG", "azores": "PT-20"}


def main():
    with urllib.request.urlopen(INDEX) as response:
        features = [feature["properties"] for feature in json.load(response)["features"]]
    children = {}
    for feature in features:
        children.setdefault(feature.get("parent"), []).append(feature)

    europe = []
    for country in sorted(children["europe"], key=lambda feature: feature["id"]):
        if country["id"] in SKIPPED:
            continue
        name = COUNTRIES.get(country["id"], country["name"])
        alpha2 = (country.get("iso3166-1:alpha2") or [CODES[country["id"]]])[0]
        parts = [part for part in children.get(country["id"], []) if part["id"] not in SKIPPED]
        if not parts:
            europe.append({
                "id": alpha2.lower(), "code": alpha2, "country": alpha2[:2], "group": "eu",
                "name": name, "summary": name, "osm": country["urls"]["pbf"],
            })
            continue
        for part in sorted(parts, key=lambda feature: feature["name"]):
            code = (part.get("iso3166-2") or [f"{alpha2}-{part['id'][:3].upper()}"])[0]
            europe.append({
                "id": f"{alpha2.lower()}-{part['id'].split('/')[-1]}", "code": code, "country": alpha2, "group": "eu",
                "name": part["name"], "summary": name, "osm": part["urls"]["pbf"],
            })

    path = ROOT / "regions.json"
    kept = [region for region in json.loads(path.read_text()) if region.get("group") != "eu"]
    path.write_text(json.dumps(kept + europe, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(europe)} zonas de Europa; {len(kept)} que ya estaban")


if __name__ == "__main__":
    main()
