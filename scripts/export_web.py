# -*- coding: utf-8 -*-
"""Export des données de la carte web (docs/data/*.geojson) depuis les GeoPackages du projet.
A lancer dans la console Python de QGIS après drias_pipeline (étapes 1 à 7) :
    import sys; sys.path.insert(0, r'<dossier projet>/scripts'); import export_web; export_web.run()
Propriétés exportées (clés courtes pour alléger les fichiers) :
    c = code, n = nom, p = population, a = point d'ancrage du graphique [lon, lat]
    pt[seuil_horizon] = parts de surface (%) [chaleur, sécheresse, feux, pluies] dans les seuil % les plus exposés
    s2 / s3 = part de la surface cumulant >= 2 / >= 3 aléas ; p3 = part de la population cumulant >= 3 aléas
    seuil_horizon : '30_27', '10_27' (France +2,7 °C, 2050), '30_40', '10_40' (France +4 °C, 2100)
    v[ref|27|40] = valeurs moyennes par an [jours Tx>=35, nuits tropicales, jours sol sec, jours IFM>=40, pluie max 1 jour (mm)]
    dt[27|40] = réchauffement moyen annuel par rapport à 1976-2005 (°C)
"""
import os, json
from qgis.core import (QgsVectorLayer, QgsGeometry, QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsProject)
import drias_pipeline as dp

THEMES = ['chaleur', 'secheresse', 'feux', 'pluies']
KEYS = [(q, n) for n in ('p27', 'p40') for q in (30, 10)]
RAW = ['tx35', 'nt', 'swi04', 'ifm40', 'rx1d']


def run(tolerances=(('departement', 500), ('epci', 350))):
    web = os.path.join(dp.BASE, 'docs', 'data')
    os.makedirs(web, exist_ok=True)
    tr = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:2154'), QgsCoordinateReferenceSystem('EPSG:4326'),
                                QgsProject.instance())
    res = {}
    for lvl, tol in tolerances:
        lyr = QgsVectorLayer(f'{dp.GPKG}|layername={lvl}_indicateurs', lvl, 'ogr')
        feats = []
        for f in lyr.getFeatures():
            g = QgsGeometry(f.geometry())
            pos = g.pointOnSurface()
            gs = g.simplify(tol)
            if gs.isEmpty():
                gs = g
            gs.transform(tr)
            pos.transform(tr)
            k = lambda q, n: f'{q}_{n[1:]}'
            props = {'c': f['code'], 'n': f['nom'], 'p': int(f['population'] or 0),
                     'a': [round(pos.asPoint().x(), 4), round(pos.asPoint().y(), 4)],
                     'pt': {k(q, n): [round(f[f'pt_{t}_top{q}_{n}'] or 0) for t in THEMES] for q, n in KEYS},
                     's3': {k(q, n): round(f[f'surfcum3_top{q}_{n}'] or 0) for q, n in KEYS},
                     's2': {k(q, n): round(f[f'surfcum2_top{q}_{n}'] or 0) for q, n in KEYS},
                     'p3': {k(q, n): round(f[f'popcum3_top{q}_{n}'] or 0) for q, n in KEYS},
                     'v': {h: [None if f[f'{r}_{n}'] is None else round(f[f'{r}_{n}'], 1) for r in RAW]
                           for h, n in (('ref', 'ref'), ('27', 'p27'), ('40', 'p40'))},
                     'dt': {'27': round(f['dtm_p27'], 1), '40': round(f['dtm_p40'], 1)}}
            feats.append({'type': 'Feature', 'properties': props, 'geometry': json.loads(gs.asJson(3))})
        s = json.dumps({'type': 'FeatureCollection', 'features': feats}, ensure_ascii=False, separators=(',', ':'))
        with open(os.path.join(web, f'{lvl}s.geojson'), 'w', encoding='utf-8') as fh:
            fh.write(s)
        res[lvl] = len(feats)
    return res
