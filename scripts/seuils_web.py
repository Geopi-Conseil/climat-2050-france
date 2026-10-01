# -*- coding: utf-8 -*-
"""Deux modes de lecture pour la carte web (sans QGIS : lit le GeoPackage en SQLite).

  mode « relatif »  : seuils 30 % / 10 % recalculés à chaque horizon (comparer les territoires entre eux)
  mode « fixe »     : seuils 30 % / 10 % de la période de référence 1976-2005, appliqués tels quels
                      en 2050 et 2100 (mesurer le basculement par rapport au climat d'hier)

Entrées  : data/drias_tracc2023_q50.gpkg (couche communes_indicateurs), data/seuils_cumuls.json
Sorties  : propriétés ajoutées à docs/data/departements.geojson et docs/data/epcis.geojson
             ptr[q_h] = parts de surface (%) [chaleur, sécheresse, feux, pluies] au-dessus du seuil de référence
             sr2 / sr3[q_h] = part de la surface cumulant >= 2 / >= 3 aléas (mode fixe)
             pr3[q_h] = part de la population cumulant >= 3 aléas (mode fixe)
             (q_h : '30_ref', '10_ref', '30_27', '10_27', '30_40', '10_40')
           docs/data/synthese.json : chiffres nationaux des deux modes
Usage    : python scripts/seuils_web.py   (depuis le dossier du projet)
"""
import json
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GPKG = os.path.join(BASE, 'data', 'drias_tracc2023_q50.gpkg')
SEUILS = os.path.join(BASE, 'data', 'seuils_cumuls.json')
WEB = os.path.join(BASE, 'docs', 'data')
THEMES = ['chaleur', 'secheresse', 'feux', 'pluies']
NIV = [('ref', 'ref'), ('27', 'p27'), ('40', 'p40')]
PARTS = [30, 10]


def run():
    seuils = json.load(open(SEUILS, encoding='utf-8'))
    con = sqlite3.connect('file:' + GPKG + '?mode=ro', uri=True)
    cols = ['code_insee_du_departement', 'codes_siren_des_epci', 'surf_km2', 'population']
    cols += [f'i_{t}_{n}' for t in THEMES for _, n in NIV]
    rows = [dict(zip(cols, r)) for r in con.execute('select ' + ','.join(cols) + ' from communes_indicateurs')]

    # minimum de chaque indice (les ex aequo au minimum ne comptent jamais, comme dans etape5_cumuls)
    mins = {f'i_{t}_{n}': min(r[f'i_{t}_{n}'] for r in rows if r[f'i_{t}_{n}'] is not None)
            for t in THEMES for _, n in NIV}

    def flags(r, mode, q, n):
        out = []
        for t in THEMES:
            v = r[f'i_{t}_{n}']
            ref_n = 'ref' if mode == 'fixe' else n
            thr = seuils[f'i_{t}_{ref_n}|top{q}']
            out.append(v is not None and v >= thr and v > mins[f'i_{t}_{n}'])
        return out

    # ---- agrégation dépt / EPCI (mode fixe) + synthèse nationale (deux modes)
    agg = {'departement': {}, 'epci': {}}
    nat = {}
    stot = sum(r['surf_km2'] or 0 for r in rows)
    for r in rows:
        s, p = r['surf_km2'] or 0.0, r['population'] or 0
        keys = {'departement': r['code_insee_du_departement'],
                'epci': (r['codes_siren_des_epci'] or '').split('/')[0]}
        for q in PARTS:
            for h, n in NIV:
                k = f'{q}_{h}'
                for mode in ('fixe', 'relatif'):
                    fl = flags(r, mode, q, n)
                    nb = sum(fl)
                    a = nat.setdefault(mode, {}).setdefault(k, {'s3': 0.0, 'p3': 0, 'st': [0.0] * 4, 'pt': [0] * 4})
                    if nb >= 3:
                        a['s3'] += s
                        a['p3'] += p
                    for i, f in enumerate(fl):
                        if f:
                            a['st'][i] += s
                            a['pt'][i] += p
                    if mode != 'fixe':
                        continue
                    for lvl, code in keys.items():
                        if not code or code == 'NC':
                            continue
                        g = agg[lvl].setdefault(code, {'s': 0.0, 'p': 0, 'd': {}})
                        d = g['d'].setdefault(k, {'t': [0.0] * 4, 's2': 0.0, 's3': 0.0, 'p3': 0})
                        for i, f in enumerate(fl):
                            if f:
                                d['t'][i] += s
                        if nb >= 2:
                            d['s2'] += s
                        if nb >= 3:
                            d['s3'] += s
                            d['p3'] += p
        for lvl, code in keys.items():
            if code and code != 'NC':
                g = agg[lvl].setdefault(code, {'s': 0.0, 'p': 0, 'd': {}})
                g['s'] += s
                g['p'] += p

    synth = {mode: {k: {'s3': round(100 * v['s3'] / stot, 1), 'p3': round(v['p3'] / 1e6, 1),
                        'st': [round(100 * x / stot, 1) for x in v['st']],
                        'pt': [round(x / 1e6, 1) for x in v['pt']]} for k, v in d.items()}
             for mode, d in nat.items()}
    with open(os.path.join(WEB, 'synthese.json'), 'w', encoding='utf-8') as fh:
        json.dump(synth, fh, ensure_ascii=False, indent=1)

    # ---- écriture dans les GeoJSON
    for lvl, fn in (('departement', 'departements.geojson'), ('epci', 'epcis.geojson')):
        path = os.path.join(WEB, fn)
        gj = json.load(open(path, encoding='utf-8'))
        for f in gj['features']:
            g = agg[lvl].get(f['properties']['c'])
            if not g or not g['s']:
                continue
            pr = f['properties']
            pr['ptr'] = {k: [round(100 * x / g['s']) for x in d['t']] for k, d in g['d'].items()}
            pr['sr2'] = {k: round(100 * d['s2'] / g['s']) for k, d in g['d'].items()}
            pr['sr3'] = {k: round(100 * d['s3'] / g['s']) for k, d in g['d'].items()}
            pr['pr3'] = {k: round(100 * d['p3'] / g['p']) if g['p'] else 0 for k, d in g['d'].items()}
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(json.dumps(gj, ensure_ascii=False, separators=(',', ':')))
    return synth


if __name__ == '__main__':
    s = run()
    for mode in s:
        for k in ('10_ref', '10_27', '10_40', '30_27', '30_40'):
            print(mode, k, s[mode][k]['s3'], '% surf ≥3 aléas,', s[mode][k]['p3'], 'M hab | par aléa (% surf):', s[mode][k]['st'])
