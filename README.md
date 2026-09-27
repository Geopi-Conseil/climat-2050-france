# Climat 2050 : quels seront les aléas climatiques dominants sur votre territoire ?

Chaleur, sécheresse, feux de forêt, pluies extrêmes : quels départements et quelles intercommunalités de l'Hexagone seront les plus exposés dans une France à **+2,7 °C (2050)** et **+4 °C (2100)** ?

**➡ Carte interactive : https://geopi-conseil.github.io/climat-2050-france/**

![Aperçu](docs/img/visuel_synthese.jpg)

## Ce que montre la carte

Pour chaque département et chaque EPCI, quatre barres indiquent la **part de la surface du territoire** comprise dans les **30 %** (ou **10 %**) de l'Hexagone les plus exposés à chacun des quatre aléas. Le fond gris indique la part de la surface qui **cumule au moins trois aléas**.

| Aléa | Variables DRIAS (TRACC-2023) |
|---|---|
| Chaleur | jours avec Tx ≥ 35 °C · nuits tropicales (Tn ≥ 20 °C) · température maximale moyenne en été |
| Sécheresse | jours de sol sec (SWI < 0,4) · cumul de pluie de juin à août (inversé) |
| Feux de forêt | jours avec Indice Forêt Météo (IFM) ≥ 40 |
| Pluies extrêmes | pluie maximale en une journée · 99ᵉ centile des pluies quotidiennes |

## Méthode (résumé)

1. **Données** : DRIAS / Météo-France, « Quantiles des indicateurs annuels TRACC-2023 moyennés par niveau de réchauffement », médiane (Q50) de l'ensemble des simulations, grille SAFRAN 8 km (8 981 mailles) ; niveaux : référence 1976-2005, France +2 °C, +2,7 °C et +4 °C.
2. **Mailles → communes** : moyenne des mailles pondérée par la surface d'intersection (34 748 communes, IGN ADMIN EXPRESS COG CARTO).
3. **Notes 0-100** : chaque variable est normalisée entre ses percentiles 2 et 98 (bornes communes à tous les horizons) ; note d'un aléa = moyenne de ses variables.
4. **Seuils 30 % / 10 %** : pour chaque aléa et chaque horizon, communes situées dans les 30 % (10 %) du territoire national les plus exposés, avec des percentiles **pondérés par la surface**.
5. **Agrégation** : part de la surface de chaque département / EPCI dans ces zones, aléa par aléa ; part de la surface et de la population cumulant ≥ 2 et ≥ 3 aléas.

Détails complets : [`LISEZMOI_methode.md`](LISEZMOI_methode.md) et section « Méthode » de la page.

### Précautions de lecture
- Classement **relatif** : les seuils sont recalculés pour chaque horizon ; un territoire « sans barre » n'est pas épargné.
- Il s'agit d'un **aléa climatique**, pas d'un risque : ni la végétation (feux), ni la vulnérabilité, ni la ressource en eau ne sont prises en compte.
- Moyennes pluriannuelles, résolution de 8 km.

## Organisation du dépôt

```
docs/                     page web publiée par GitHub Pages
  index.html
  assets/                 style.css, app.js, vendor/leaflet
  data/                   departements.geojson, epcis.geojson (géométries simplifiées)
  img/
scripts/
  drias_pipeline.py       chaîne de traitement PyQGIS (étapes 1 à 7)
  export_web.py           export des GeoJSON de la page
data/                     synthèses (seuils, bornes de normalisation, cumuls nationaux)
exports/                  planches cartographiques commentées (PNG)
LISEZMOI_methode.md       méthode détaillée
```

Les GeoPackages de travail (~450 Mo), le projet QGIS et les fichiers DRIAS bruts ne sont pas versionnés.

## Reproduire l'analyse

1. Commander sur [drias-climat.fr](https://www.drias-climat.fr/) (espace Données et produits → TRACC-2023) le produit « Quantiles des indicateurs annuels TRACC-2023 moyennés par niveau de réchauffement », jeu **Q50**, **France entière**, pour les 4 niveaux (référence, +2 °C, +2,7 °C, +4 °C) et les indicateurs `NORTMm_yr, NORTXm_seas_JJA, NORTX35D_yr, NORTX30D_yr, NORTR_yr, NORRR_yr, NORRR_seas_JJA, NORRRq99_yr, NORRx1d_yr, NORIFM40_yr, NORSWI04_yr` ; déposer les fichiers `.txt` dans `data/drias_brut/`.
2. Récupérer ADMIN EXPRESS COG CARTO (régions, départements, EPCI, communes) dans `data/admin/admin_express_metropole.gpkg` (service WFS de la Géoplateforme IGN).
3. Dans la console Python de QGIS (3.34+) :
   ```python
   import sys; sys.path.insert(0, r'<dossier du projet>/scripts')
   import drias_pipeline as dp, export_web
   dp.etape1_grille(); dp.etape2_communes(); dp.etape3_indices(); dp.etape4_agregats()
   dp.etape5_cumuls(); dp.etape6_cumuls_agregats('p27'); dp.etape6_cumuls_agregats('p40'); dp.etape7_parts_themes()
   export_web.run()
   ```

## Sources et crédits

- Projections climatiques : **DRIAS, les futurs du climat (Météo-France)**, jeu TRACC-2023.
- Limites administratives et population : **IGN, ADMIN EXPRESS COG CARTO** (Licence Ouverte Etalab 2.0).
- Cartographie web : [Leaflet](https://leafletjs.com) (BSD-2-Clause) ; fond de carte © IGN, Plan IGN (Géoplateforme).

Conception et analyse : **Josselin Thonnelier**, [Géopi Conseil](https://geopi-conseil.github.io/), 2026.
