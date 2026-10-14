#!/usr/bin/env python3
"""Añade a regions.json y graphs.json las zonas y las redes de carreteras de Europa, a partir del
índice de extractos de Geofabrik.

    ./europe.py

Cada país entra entero, salvo los que Geofabrik reparte en regiones (Francia, Alemania, Italia…),
que entran región a región para que ningún fichero pase de los 2 GB que admite una Release.
La red de carreteras es una por país, entera, para que las rutas crucen de una región a otra.
España no se toca: sus comunidades están escritas a mano, con sus nombres en español.
"""
import json
import pathlib
import sys
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


# Nombre en español de cada región, por su identificador en regions.json. Geofabrik los da en el
# idioma local y a veces con HTML («Nord-Norge<br />(Northern Norway)»).
REGIONS = {
    "cz-jihomoravsky": "Moravia Meridional", "cz-jihocesky": "Bohemia Meridional", "cz-karlovarsky": "Karlovy Vary",
    "cz-vysocina": "Vysočina", "cz-kralovehradecky": "Hradec Králové", "cz-liberecky": "Liberec",
    "cz-moravskoslezky": "Moravia-Silesia", "cz-olomoucky": "Olomouc", "cz-pardubicky": "Pardubice",
    "cz-plzensky": "Pilsen", "cz-praha": "Praga", "cz-stredocesky": "Bohemia Central (con Praga)", "cz-zlinsky": "Zlín",
    "cz-ustecky": "Ústí nad Labem",
    "fr-alsace": "Alsacia", "fr-aquitaine": "Aquitania", "fr-auvergne": "Auvernia", "fr-basse-normandie": "Baja Normandía",
    "fr-bourgogne": "Borgoña", "fr-bretagne": "Bretaña", "fr-centre": "Centro-Valle del Loira",
    "fr-champagne-ardenne": "Champaña-Ardenas", "fr-corse": "Córcega", "fr-franche-comte": "Franco Condado",
    "fr-guadeloupe": "Guadalupe", "fr-guyane": "Guayana Francesa", "fr-haute-normandie": "Alta Normandía",
    "fr-ile-de-france": "Isla de Francia", "fr-languedoc-roussillon": "Languedoc-Rosellón", "fr-limousin": "Lemosín",
    "fr-lorraine": "Lorena", "fr-martinique": "Martinica", "fr-mayotte": "Mayotte", "fr-midi-pyrenees": "Mediodía-Pirineos",
    "fr-nord-pas-de-calais": "Norte-Paso de Calais", "fr-pays-de-la-loire": "País del Loira", "fr-picardie": "Picardía",
    "fr-poitou-charentes": "Poitou-Charentes", "fr-provence-alpes-cote-d-azur": "Provenza-Alpes-Costa Azul",
    "fr-reunion": "Reunión", "fr-rhone-alpes": "Ródano-Alpes",
    "de-baden-wuerttemberg": "Baden-Wurtemberg", "de-bayern": "Baviera", "de-berlin": "Berlín",
    "de-brandenburg": "Brandeburgo (con Berlín)", "de-bremen": "Bremen", "de-hamburg": "Hamburgo", "de-hessen": "Hesse",
    "de-mecklenburg-vorpommern": "Mecklemburgo-Pomerania Occidental", "de-niedersachsen": "Baja Sajonia (con Bremen)",
    "de-nordrhein-westfalen": "Renania del Norte-Westfalia", "de-rheinland-pfalz": "Renania-Palatinado",
    "de-saarland": "Sarre", "de-sachsen": "Sajonia", "de-sachsen-anhalt": "Sajonia-Anhalt",
    "de-schleswig-holstein": "Schleswig-Holstein", "de-thueringen": "Turingia",
    "it-centro": "Centro de Italia", "it-isole": "Sicilia y Cerdeña", "it-nord-est": "Noreste de Italia",
    "it-nord-ovest": "Noroeste de Italia", "it-sud": "Sur de Italia",
    "nl-drenthe": "Drente", "nl-flevoland": "Flevoland", "nl-friesland": "Frisia", "nl-gelderland": "Güeldres",
    "nl-groningen": "Groninga", "nl-limburg": "Limburgo", "nl-noord-brabant": "Brabante Septentrional",
    "nl-noord-holland": "Holanda Septentrional", "nl-overijssel": "Overijssel", "nl-utrecht": "Utrecht",
    "nl-zeeland": "Zelanda", "nl-zuid-holland": "Holanda Meridional",
    "no-nord-norge": "Norte de Noruega", "no-sorlandet": "Sur de Noruega", "no-trondelag": "Trøndelag",
    "no-vestlandet": "Noruega Occidental", "no-ostlandet": "Noruega Oriental",
    "pl-dolnoslaskie": "Baja Silesia", "pl-kujawsko-pomorskie": "Cuyavia y Pomerania", "pl-lubelskie": "Lublin",
    "pl-lubuskie": "Lubusz", "pl-mazowieckie": "Mazovia", "pl-malopolskie": "Pequeña Polonia", "pl-opolskie": "Opole",
    "pl-podkarpackie": "Subcarpacia", "pl-podlaskie": "Podlaquia", "pl-pomorskie": "Pomerania",
    "pl-warminsko-mazurskie": "Varmia y Masuria", "pl-wielkopolskie": "Gran Polonia",
    "pl-zachodniopomorskie": "Pomerania Occidental", "pl-lodzkie": "Łódź", "pl-slaskie": "Silesia",
    "pl-swietokrzyskie": "Santa Cruz",
    "gb-england": "Inglaterra", "gb-scotland": "Escocia", "gb-wales": "Gales",
}


# Códigos de los territorios que el índice deja sin código de país.
CODES = {"kosovo": "XK", "isle-of-man": "IM", "guernsey-jersey": "GG", "azores": "PT-20"}


def main():
    with urllib.request.urlopen(INDEX) as response:
        features = [feature["properties"] for feature in json.load(response)["features"]]
    children = {}
    for feature in features:
        children.setdefault(feature.get("parent"), []).append(feature)

    europe, networks = [], {}
    for country in sorted(children["europe"], key=lambda feature: feature["id"]):
        if country["id"] in SKIPPED:
            continue
        name = COUNTRIES.get(country["id"], country["name"])
        alpha2 = (country.get("iso3166-1:alpha2") or [CODES[country["id"]]])[0]
        parts = [part for part in children.get(country["id"], []) if part["id"] not in SKIPPED]
        graph = alpha2.lower()
        networks[graph] = {"group": "eu", "osm": country["urls"]["pbf"]}
        if not parts:
            europe.append({
                "id": graph, "code": alpha2, "country": alpha2[:2], "group": "eu", "graph": graph,
                "name": name, "summary": name, "osm": country["urls"]["pbf"],
            })
            continue
        for part in sorted(parts, key=lambda feature: feature["name"]):
            code = (part.get("iso3166-2") or [f"{alpha2}-{part['id'][:3].upper()}"])[0]
            region_id = f"{alpha2.lower()}-{part['id'].split('/')[-1]}"
            if region_id not in REGIONS:
                sys.exit(f"Falta el nombre en español de {region_id} ({part['name']}) en REGIONS")
            europe.append({
                "id": region_id, "code": code, "country": alpha2, "group": "eu", "graph": graph,
                "name": REGIONS[region_id], "summary": name, "osm": part["urls"]["pbf"],
            })

    path = ROOT / "regions.json"
    kept = [region for region in json.loads(path.read_text()) if region.get("group") != "eu"]
    path.write_text(json.dumps(kept + europe, ensure_ascii=False, indent=2) + "\n")
    graphs_path = ROOT / "graphs.json"
    kept_graphs = {graph: details for graph, details in json.loads(graphs_path.read_text()).items() if details.get("group") != "eu"}
    graphs_path.write_text(json.dumps({**kept_graphs, **networks}, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(europe)} zonas y {len(networks)} redes de Europa; {len(kept)} zonas que ya estaban")


if __name__ == "__main__":
    main()
