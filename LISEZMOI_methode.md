# Territoires exposés au changement climatique (DRIAS TRACC-2023)

Projet QGIS : `DRIAS_exposition_climat.qgz` (Lambert 93, France métropolitaine)

## Données
- **DRIAS** : « Quantiles des indicateurs annuels TRACC-2023 moyennés par niveau de réchauffement », médiane d'ensemble (Q50), 8 981 points SAFRAN (8 km). Requêtes 2026000028373 (référence), 374 (+2 °C, 2030), 375 (+2,7 °C, 2050), 376 (+4 °C, 2100). Fichiers bruts dans `data/drias_brut/`.
- **IGN ADMIN EXPRESS COG CARTO** (dernière édition, Géoplateforme WFS) : régions, départements, EPCI, communes avec population INSEE. Fichier : `data/admin/admin_express_metropole.gpkg`.

## Indicateurs (nom de champ = code_niveau, ex. `tx35_p27`)
| Champ | Indicateur DRIAS |
|---|---|
| tm | Température moyenne annuelle (°C) |
| txete | Température maximale moyenne en été (°C) |
| tx35 / tx30 | Jours avec Tx ≥ 35 °C / ≥ 30 °C |
| nt | Nuits tropicales (Tn ≥ 20 °C) |
| rr / rrete | Cumul de précipitations annuel / estival (mm) |
| rq99 | Cumul quotidien remarquable, P99 (mm) |
| rx1d | Pluie journalière maximale annuelle (mm) |
| ifm40 | Jours avec Indice Feu Météo ≥ 40 |
| swi04 | Jours de sol sec (SWI < 0,4) |

Suffixes : `ref` = 1976-2005, `p20` = +2 °C, `p27` = +2,7 °C, `p40` = +4 °C. Préfixe `d` = écart au niveau de référence.

## Méthode
1. **Mailles SAFRAN** : carrés de 8 km reconstruits en Lambert II étendu autour de chaque point, puis reprojetés (`mailles_safran`).
2. **Communes** : moyenne des mailles pondérée par la surface d'intersection (`communes_indicateurs`). 4 communes insulaires hors grille reçoivent la maille la plus proche.
3. **Indices thématiques (0-100)** : chaque indicateur est normalisé entre ses percentiles 2 et 98, calculés sur les 4 niveaux ensemble. Les cartes des différents horizons sont donc comparables.
   - Chaleur = moyenne de tx35, nt et txete
   - Sécheresse = moyenne de swi04 et de rrete inversé
   - Feux = ifm40
   - Pluies extrêmes = moyenne de rx1d et rq99
4. **Indice composite** = moyenne des 4 thèmes, sans pondération. Les classes `cl_composite_*` (1 à 5) sont les quintiles des communes à +2,7 °C, appliqués à tous les horizons. Les seuils sont dans `data/bornes_normalisation.json`.
5. **EPCI et départements** : moyenne des communes pondérée par la surface. Les champs `pop_communes_q5_p27` et `part_pop_q5_p27` donnent la population des communes de la classe 5 à +2,7 °C.

## Limites
- L'indice mesure l'**aléa climatique**, pas la vulnérabilité (sensibilité, capacité d'adaptation). La population n'est présente qu'à titre d'information sur les enjeux.
- La résolution de 8 km lisse les effets locaux : îlots de chaleur urbains, relief fin, littoral.
- La médiane Q50 masque la dispersion des modèles. Les produits MIN/MAX de DRIAS permettent de l'évaluer.

## Relancer les calculs
Dans la console Python de QGIS :
```python
import sys; sys.path.insert(0, r'C:\Users\33632\Desktop\SIG\climat_extreme-2050-france\scripts')
import drias_pipeline as dp
dp.etape1_grille(); dp.etape2_communes(); dp.etape3_indices(); dp.etape4_agregats()
```
Les pondérations des thèmes se modifient dans le dictionnaire `THEMES` du script.

## Cumul des aléas (groupe « Cumul des aléas »)
Pour chaque horizon et chacun des 4 thèmes, on retient les communes situées dans les **50 %, 30 % et 10 % du territoire** les plus exposés. Les seuils sont des percentiles pondérés par la surface des communes, pour ne pas surreprésenter les régions où les communes sont petites. On compte ensuite combien de thèmes dépassent le seuil.
- `nth_top{50|30|10}_{niveau}` : nombre de thèmes cumulés (0 à 4)
- `nvar_top..._{niveau}` : même calcul sur les 8 variables brutes (0 à 8)
- `th_top..._{niveau}` : liste des thèmes cumulés, par exemple « Chaleur + Sécheresse + Feux »
- EPCI et départements : `surfcum{2|3}_top{30|10}_{p27|p40}` et `popcum...` donnent la part de la surface et de la population cumulant au moins 2 ou 3 thèmes.

Les seuils sont **relatifs à chaque horizon** : on compare les territoires entre eux, pas le niveau absolu de l'aléa. Les seuils utilisés sont dans `data/seuils_cumuls.json`, la synthèse chiffrée dans `data/synthese_cumuls.json`.

## Deux modes de lecture (carte web)
Les seuils ci-dessus sont **relatifs à chaque horizon** (mode *Classement*) : la surface retenue reste par construction de 30 % ou 10 % du territoire à chaque horizon. Ce mode répond à la question « quels territoires seront les plus exposés par rapport aux autres ? », mais il ne montre pas l'aggravation dans le temps : un territoire peut « perdre » un aléa entre 2050 et 2100 simplement parce que d'autres territoires le dépassent.

La carte web propose donc un second mode, *Basculement* (affiché par défaut, au seuil de 10 %) :
- les seuils des 10 % et 30 % les plus exposés sont calculés sur la **période de référence 1976-2005** (`i_{thème}_ref|top{q}` dans `data/seuils_cumuls.json`) ;
- ces mêmes seuils sont appliqués aux notes de 2050 (+2,7 °C) et 2100 (+4 °C) ; les notes 0-100 ayant des bornes communes à tous les horizons, la comparaison est directe ;
- une commune ex aequo au minimum de l'indice n'est jamais retenue (même règle que `etape5_cumuls`).

Le calcul est fait par `scripts/seuils_web.py` (Python seul, lecture du GeoPackage en SQLite). Il ajoute aux GeoJSON de la page les champs `ptr`, `sr2`, `sr3`, `pr3` (clés `30_ref`, `10_ref`, `30_27`, `10_27`, `30_40`, `10_40`) et écrit la synthèse nationale des deux modes dans `docs/data/synthese.json`.

Ordres de grandeur, Hexagone, part de la surface cumulant au moins 3 aléas (population concernée) :

| Seuil | 1976-2005 | 2050 (+2,7 °C) | 2100 (+4 °C) |
|---|---|---|---|
| Basculement 10 % | 5,8 % (7,7 M hab.) | 20,3 % (16,8 M hab.) | 41,7 % (30,9 M hab.) |
| Basculement 30 % | 15,4 % (16,9 M hab.) | 59,7 % (45,7 M hab.) | 80,5 % (55,3 M hab.) |
| Classement 10 % | 5,8 % (7,7 M hab.) | 6,1 % (8,0 M hab.) | 5,6 % (7,3 M hab.) |
| Classement 30 % | 15,4 % (16,9 M hab.) | 14,1 % (14,7 M hab.) | 14,6 % (13,5 M hab.) |


## Diagrammes par territoire (groupe « Diagrammes par territoire »)
Un histogramme est placé au centroïde de chaque département ou EPCI. Chaque barre donne, pour un aléa, la part de la surface du territoire située dans les 30 % (ou 10 %) du territoire national les plus exposés. Les champs utilisés sont `pt_{chaleur|secheresse|feux|pluies}_top{30|10}_{p27|p40}` (calcul : `etape7_parts_themes`).
- Échelle : une barre de 14 mm correspond à 100 % pour les départements, 9 mm pour les EPCI. Les diagrammes des EPCI ne s'affichent qu'en dessous du 1:3 000 000.
- Le fond gris donne la part de la surface qui cumule au moins 3 aléas.
- En Île-de-France, les diagrammes de Paris et de la petite couronne se chevauchent : il faut zoomer ou utiliser la couche EPCI.
- Planches exportées : `exports/diagrammes_departements_top{30|10}_{p27|p40}.png`.
