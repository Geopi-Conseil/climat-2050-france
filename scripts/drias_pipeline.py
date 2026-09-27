# -*- coding: utf-8 -*-
"""Pipeline DRIAS TRACC-2023 (Q50) -> mailles SAFRAN -> communes / EPCI / departements.
Projet : Territoires exposes au changement climatique (France metropolitaine).
Usage dans la console Python QGIS :
    import sys; sys.path.insert(0, r'<dossier projet>/scripts'); import drias_pipeline as dp
    dp.etape1_grille(); dp.etape2_communes(); dp.etape3_indices(); dp.etape4_agregats()
"""
import os, glob, json, math, bisect
from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY, QgsFields, QgsField,
                       QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject,
                       QgsVectorFileWriter, QgsSpatialIndex, QgsWkbTypes, QgsCoordinateTransformContext,
                       QgsFeatureRequest)
from qgis.PyQt.QtCore import QVariant

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # dossier du projet (parent de scripts/)
BRUT = os.path.join(BASE, 'data', 'drias_brut')
ADMIN = os.path.join(BASE, 'data', 'admin')
GPKG_ADMIN = os.path.join(ADMIN, 'admin_express_metropole.gpkg')
GPKG = os.path.join(BASE, 'data', 'drias_tracc2023_q50.gpkg')
OUTRE_MER = ('01', '02', '03', '04', '06')

# code DRIAS -> nom court de champ
IND = {'NORTMm_yr': 'tm', 'NORTXm_seas_JJA': 'txete', 'NORTX35D_yr': 'tx35', 'NORTX30D_yr': 'tx30',
       'NORTR_yr': 'nt', 'NORRR_yr': 'rr', 'NORRR_seas_JJA': 'rrete', 'NORRRq99_yr': 'rq99',
       'NORRx1d_yr': 'rx1d', 'NORIFM40_yr': 'ifm40', 'NORSWI04_yr': 'swi04'}
# niveau DRIAS -> suffixe (ref, France +2 / +2,7 / +4 degres)
NIV = {'REF': 'ref', 'GWL15': 'p20', 'GWL20': 'p27', 'GWL30': 'p40'}
NIVS = ['ref', 'p20', 'p27', 'p40']
FUTURS = ['p20', 'p27', 'p40']


def champs_valeurs():
    noms = []
    for s in IND.values():
        for n in NIVS:
            noms.append(f'{s}_{n}')
        for n in FUTURS:
            noms.append(f'd{s}_{n}')          # ecart absolu au niveau de reference
    return noms


def _ecrire(layer, gpkg, nom):
    o = QgsVectorFileWriter.SaveVectorOptions()
    o.driverName = 'GPKG'
    o.layerName = nom
    o.actionOnExistingFile = (QgsVectorFileWriter.CreateOrOverwriteLayer if os.path.exists(gpkg)
                              else QgsVectorFileWriter.CreateOrOverwriteFile)
    r = QgsVectorFileWriter.writeAsVectorFormatV3(layer, gpkg, QgsCoordinateTransformContext(), o)
    if r[0] != 0:
        raise RuntimeError(f'Ecriture {nom} : {r}')
    return f'{gpkg}|layername={nom}'


# ----------------------------------------------------------------------------------------------
def lire_drias():
    """Lit tous les .txt DRIAS (y compris un fichier regroupant plusieurs extractions)."""
    data, niveaux = {}, set()
    for f in sorted(glob.glob(os.path.join(BRUT, '*.txt'))):
        cols = None
        with open(f, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                line = line.strip()
                if line.startswith('# Point;'):
                    cols = [c for c in line[2:].split(';') if c]
                    continue
                if not line or line[0] in '#@' or cols is None:
                    continue
                rec = dict(zip(cols, line.split(';')))
                niv = NIV.get(rec['Niveau'].strip())
                if niv is None:
                    raise ValueError(f"Niveau inconnu {rec['Niveau']} dans {f}")
                niveaux.add(niv)
                p = int(rec['Point'])
                d = data.setdefault(p, {'lat': float(rec['Latitude']), 'lon': float(rec['Longitude']), 'v': {}})
                for code, s in IND.items():
                    txt = rec.get(code, '').strip()
                    if txt != '':
                        d['v'][f'{s}_{niv}'] = float(txt)
    return data, niveaux


def etape1_grille():
    """Construit les mailles SAFRAN 8 km (carres dans le Lambert II etendu) avec toutes les valeurs."""
    data, niveaux = lire_drias()
    manquants = [n for n in NIVS if n not in niveaux]
    wgs = QgsCoordinateReferenceSystem('EPSG:4326')
    l2e = QgsCoordinateReferenceSystem('EPSG:27572')
    l93 = QgsCoordinateReferenceSystem('EPSG:2154')
    t1 = QgsCoordinateTransform(wgs, l2e, QgsProject.instance())
    t2 = QgsCoordinateTransform(l2e, l93, QgsProject.instance())
    noms = champs_valeurs()
    lyr = QgsVectorLayer('Polygon?crs=EPSG:2154', 'mailles_safran', 'memory')
    pr = lyr.dataProvider()
    flds = [QgsField('point', QVariant.Int), QgsField('lat', QVariant.Double), QgsField('lon', QVariant.Double),
            QgsField('x_l2e', QVariant.Double), QgsField('y_l2e', QVariant.Double)]
    flds += [QgsField(n, QVariant.Double) for n in noms]
    pr.addAttributes(flds)
    lyr.updateFields()
    feats = []
    # centres en Lambert II etendu, recales sur la grille reguliere de 8 km (les lat/lon DRIAS sont
    # arrondies a 1e-4 degre, soit ~10 m d'erreur) pour que les mailles se jointoient sans trou
    proj = {p: t1.transform(QgsPointXY(d['lon'], d['lat'])) for p, d in data.items()}
    offx = sorted(c.x() % 8000 for c in proj.values())[len(proj) // 2]
    offy = sorted(c.y() % 8000 for c in proj.values())[len(proj) // 2]
    for p, d in data.items():
        c = proj[p]
        cx = round((c.x() - offx) / 8000) * 8000 + offx
        cy = round((c.y() - offy) / 8000) * 8000 + offy
        ring = [QgsPointXY(cx - 4000, cy - 4000), QgsPointXY(cx + 4000, cy - 4000),
                QgsPointXY(cx + 4000, cy + 4000), QgsPointXY(cx - 4000, cy + 4000)]
        g = QgsGeometry.fromPolygonXY([ring])
        g = g.densifyByCount(3)
        g.transform(t2)
        f = QgsFeature(lyr.fields())
        f.setGeometry(g)
        v = d['v']
        attrs = [p, d['lat'], d['lon'], c.x(), c.y()]
        for n in noms:
            if n.startswith('d') and n[1:].rsplit('_', 1)[0] in IND.values():
                s, niv = n[1:].rsplit('_', 1)
                a, b = v.get(f'{s}_{niv}'), v.get(f'{s}_ref')
                attrs.append(None if a is None or b is None else round(a - b, 3))
            else:
                attrs.append(v.get(n))
        f.setAttributes(attrs)
        feats.append(f)
    pr.addFeatures(feats)
    src = _ecrire(lyr, GPKG, 'mailles_safran')
    return {'points': len(data), 'niveaux': sorted(niveaux), 'niveaux_manquants': manquants, 'source': src}


# ----------------------------------------------------------------------------------------------
def etape0_admin():
    """Assemble les pages GeoJSON IGN (communes, regions) dans le GeoPackage admin, metropole seule."""
    res = {}
    for t, champ_reg in [('region', 'code_insee'), ('commune', 'code_insee_de_la_region')]:
        pages = sorted(glob.glob(os.path.join(ADMIN, f'_{t}_[0-9][0-9].geojson')))
        if not pages:
            continue
        base = QgsVectorLayer(pages[0], t, 'ogr')
        mem = QgsVectorLayer(f'MultiPolygon?crs=EPSG:2154', t, 'memory')
        mem.dataProvider().addAttributes(base.fields().toList())
        mem.updateFields()
        n, vus = 0, set()
        for pg in pages:
            l = QgsVectorLayer(pg, t, 'ogr')
            fs = []
            for f in l.getFeatures():
                if f[champ_reg] in OUTRE_MER or f['cleabs'] in vus:
                    continue
                vus.add(f['cleabs'])
                g = f.geometry()
                g.convertToMultiType()
                nf = QgsFeature(mem.fields())
                nf.setGeometry(g)
                nf.setAttributes(f.attributes())
                fs.append(nf)
            mem.dataProvider().addFeatures(fs)
            n += len(fs)
        _ecrire(mem, GPKG_ADMIN, t)
        res[t] = n
    return res


def etape2_communes():
    """Moyenne ponderee par la surface des mailles SAFRAN qui recouvrent chaque commune."""
    mailles = QgsVectorLayer(f'{GPKG}|layername=mailles_safran', 'm', 'ogr')
    communes = QgsVectorLayer(f'{GPKG_ADMIN}|layername=commune', 'c', 'ogr')
    noms = champs_valeurs()
    idx = QgsSpatialIndex()
    geoms, vals = {}, {}
    for f in mailles.getFeatures():
        idx.addFeature(f)
        geoms[f.id()] = f.geometry()
        vals[f.id()] = [f[n] for n in noms]
    out = QgsVectorLayer('MultiPolygon?crs=EPSG:2154', 'communes_indicateurs', 'memory')
    keep = ['code_insee', 'nom_officiel', 'population', 'code_insee_du_departement', 'code_insee_de_la_region',
            'codes_siren_des_epci', 'statut']
    flds = [communes.fields().field(k) for k in keep]
    flds += [QgsField('surf_km2', QVariant.Double), QgsField('dens_hab_km2', QVariant.Double),
             QgsField('couv_drias', QVariant.Double)]
    flds += [QgsField(n, QVariant.Double) for n in noms]
    out.dataProvider().addAttributes(flds)
    out.updateFields()
    feats, sans = [], 0
    for c in communes.getFeatures():
        g = c.geometry()
        area = g.area()
        acc = [0.0] * len(noms)
        wsum = [0.0] * len(noms)
        cov = 0.0
        cands = idx.intersects(g.boundingBox())
        for mid in cands:
            gi = geoms[mid]
            if not gi.intersects(g):
                continue
            w = gi.intersection(g).area()
            if w <= 0:
                continue
            cov += w
            for i, v in enumerate(vals[mid]):
                if v is not None:
                    acc[i] += w * v
                    wsum[i] += w
        if cov == 0:
            # commune littorale / insulaire hors maille : maille la plus proche
            near = idx.nearestNeighbor(g.centroid().asPoint(), 1)
            if near:
                for i, v in enumerate(vals[near[0]]):
                    if v is not None:
                        acc[i], wsum[i] = v, 1.0
            sans += 1
        nf = QgsFeature(out.fields())
        nf.setGeometry(g)
        surf = area / 1e6
        pop = c['population'] or 0
        attrs = [c[k] for k in keep] + [round(surf, 3), round(pop / surf, 1) if surf else None,
                                         round(cov / area, 3) if area else None]
        attrs += [round(acc[i] / wsum[i], 3) if wsum[i] else None for i in range(len(noms))]
        nf.setAttributes(attrs)
        feats.append(nf)
    out.dataProvider().addFeatures(feats)
    _ecrire(out, GPKG, 'communes_indicateurs')
    return {'communes': len(feats), 'hors_maille_plus_proche': sans}


# ----------------------------------------------------------------------------------------------
# Indices : chaque indicateur est ramene sur 0-100 avec des bornes communes a tous les niveaux
# (percentiles 2 et 98 de l'ensemble ref + +2 + +2,7 + +4 degres), pour que les cartes des differents
# horizons soient comparables. Score thematique = moyenne des composantes ; indice composite = moyenne
# des 4 themes.
THEMES = {
    'chaleur':    [('tx35', +1), ('nt', +1), ('txete', +1)],
    'secheresse': [('swi04', +1), ('rrete', -1)],   # moins de pluie en ete = plus expose
    'feux':       [('ifm40', +1)],
    'pluies':     [('rx1d', +1), ('rq99', +1)],
}


def _pct(sorted_vals, q):
    k = (len(sorted_vals) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def etape3_indices(couche='communes_indicateurs'):
    lyr = QgsVectorLayer(f'{GPKG}|layername={couche}', couche, 'ogr')
    pr = lyr.dataProvider()
    nouveaux = []
    for n in NIVS:
        for t in THEMES:
            nouveaux.append(f'i_{t}_{n}')
        nouveaux.append(f'i_composite_{n}')
        nouveaux.append(f'cl_composite_{n}')
    exist = [f.name() for f in lyr.fields()]
    pr.addAttributes([QgsField(n, QVariant.Double if not n.startswith('cl_') else QVariant.Int)
                      for n in nouveaux if n not in exist])
    lyr.updateFields()
    feats = list(lyr.getFeatures())
    bornes = {}
    for t, comps in THEMES.items():
        for s, sens in comps:
            allv = sorted(f[f'{s}_{n}'] for f in feats for n in NIVS if f[f'{s}_{n}'] is not None)
            bornes[s] = (_pct(allv, 0.02), _pct(allv, 0.98))
    # seuils de classes du composite : quintiles du niveau +2,7 degres (reference TRACC 2050)
    comp = {}
    for f in feats:
        for n in NIVS:
            ts = {}
            for t, comps in THEMES.items():
                sc = []
                for s, sens in comps:
                    v = f[f'{s}_{n}']
                    if v is None:
                        continue
                    lo, hi = bornes[s]
                    x = min(1.0, max(0.0, (v - lo) / (hi - lo))) if hi > lo else 0.0
                    sc.append(100 * (x if sens > 0 else 1 - x))
                ts[t] = round(sum(sc) / len(sc), 1) if sc else None
            vals = [v for v in ts.values() if v is not None]
            comp[(f.id(), n)] = (ts, round(sum(vals) / len(vals), 1) if vals else None)
    ref27 = sorted(v[1] for (fid, n), v in comp.items() if n == 'p27' and v[1] is not None)
    seuils = [_pct(ref27, q) for q in (0.2, 0.4, 0.6, 0.8)]
    fidx = {n: lyr.fields().indexOf(n) for n in nouveaux}
    changes = {}
    for f in feats:
        ch = {}
        for n in NIVS:
            ts, c = comp[(f.id(), n)]
            for t in THEMES:
                ch[fidx[f'i_{t}_{n}']] = ts[t]
            ch[fidx[f'i_composite_{n}']] = c
            ch[fidx[f'cl_composite_{n}']] = None if c is None else 1 + bisect.bisect_right(seuils, c)
        changes[f.id()] = ch
    pr.changeAttributeValues(changes)
    with open(os.path.join(BASE, 'data', 'bornes_normalisation.json'), 'w', encoding='utf-8') as fh:
        json.dump({'bornes_p2_p98': bornes, 'seuils_quintiles_composite_p27': seuils, 'themes': THEMES}, fh,
                  ensure_ascii=False, indent=1)
    return {'bornes': bornes, 'seuils_classes': seuils}


def etape4_agregats():
    """EPCI et departements : moyennes des communes ponderees par la surface + population exposee."""
    com = QgsVectorLayer(f'{GPKG}|layername=communes_indicateurs', 'c', 'ogr')
    noms = [f.name() for f in com.fields() if f.name().startswith(('i_', 'tx35_', 'nt_', 'swi04_', 'ifm40_', 'rx1d_', 'dtm_', 'tm_'))]
    noms = [n for n in noms if not n.startswith('cl_')]
    res = {}
    for niveau, cle, src_layer, src_key in [
            ('departement', 'code_insee_du_departement', 'departement', 'code_insee'),
            ('epci', 'codes_siren_des_epci', 'epci', 'code_siren')]:
        acc = {}
        for f in com.getFeatures():
            k = (f[cle] or '').split('/')[0]
            if not k or k == 'NC':
                continue
            a = acc.setdefault(k, {'s': 0.0, 'pop': 0, 'pop_q5': 0, 'v': [0.0] * len(noms), 'w': [0.0] * len(noms)})
            s = f['surf_km2'] or 0
            a['s'] += s
            a['pop'] += f['population'] or 0
            if f['cl_composite_p27'] == 5:
                a['pop_q5'] += f['population'] or 0
            for i, n in enumerate(noms):
                if f[n] is not None:
                    a['v'][i] += s * f[n]
                    a['w'][i] += s
        src = QgsVectorLayer(f'{GPKG_ADMIN}|layername={src_layer}', src_layer, 'ogr')
        out = QgsVectorLayer('MultiPolygon?crs=EPSG:2154', f'{niveau}_indicateurs', 'memory')
        flds = [QgsField('code', QVariant.String), QgsField('nom', QVariant.String),
                QgsField('population', QVariant.Int), QgsField('pop_communes_q5_p27', QVariant.Int),
                QgsField('part_pop_q5_p27', QVariant.Double)] + [QgsField(n, QVariant.Double) for n in noms]
        out.dataProvider().addAttributes(flds)
        out.updateFields()
        fs = []
        for f in src.getFeatures():
            k = f[src_key]
            if k not in acc:
                continue
            a = acc[k]
            g = f.geometry()
            g.convertToMultiType()
            nf = QgsFeature(out.fields())
            nf.setGeometry(g)
            nf.setAttributes([k, f['nom_officiel'], a['pop'], a['pop_q5'],
                              round(100 * a['pop_q5'] / a['pop'], 1) if a['pop'] else None] +
                             [round(a['v'][i] / a['w'][i], 2) if a['w'][i] else None for i in range(len(noms))])
            fs.append(nf)
        out.dataProvider().addFeatures(fs)
        _ecrire(out, GPKG, f'{niveau}_indicateurs')
        res[niveau] = len(fs)
    return res


# ----------------------------------------------------------------------------------------------
# Cumul des aleas : pour chaque horizon, on repere les communes situees dans les 50 %, 30 % et 10 %
# du TERRITOIRE les plus exposes (percentiles ponderes par la surface des communes, pour ne pas
# sur-representer les regions a petites communes), theme par theme puis variable par variable,
# et on compte combien de themes (0-4) / de variables (0-8) depassent le seuil.
PARTS = [50, 30, 10]
NOMS_THEMES = {'chaleur': 'Chaleur', 'secheresse': 'Sécheresse', 'feux': 'Feux', 'pluies': 'Pluies extrêmes'}


def _seuil_pondere(vals_poids, part):
    """Valeur au-dessus de laquelle se trouve `part` % de la surface (vals_poids = [(v, w)])."""
    vp = sorted(vals_poids)
    tot = sum(w for v, w in vp)
    cible = tot * (1 - part / 100.0)
    cum = 0.0
    for v, w in vp:
        cum += w
        if cum >= cible:
            return v
    return vp[-1][0]


def etape5_cumuls(couche='communes_indicateurs'):
    lyr = QgsVectorLayer(f'{GPKG}|layername={couche}', couche, 'ogr')
    pr = lyr.dataProvider()
    variables = [(s, sens) for comps in THEMES.values() for s, sens in comps]
    nouveaux = []
    for n in NIVS:
        for q in PARTS:
            nouveaux += [(f'nth_top{q}_{n}', QVariant.Int), (f'nvar_top{q}_{n}', QVariant.Int),
                         (f'th_top{q}_{n}', QVariant.String)]
    exist = [f.name() for f in lyr.fields()]
    pr.addAttributes([QgsField(nm, t) for nm, t in nouveaux if nm not in exist])
    lyr.updateFields()
    feats = list(lyr.getFeatures())
    surf = {f.id(): (f['surf_km2'] or 0.0) for f in feats}
    seuils, mins = {}, {}
    for n in NIVS:
        cles = [(f'i_{t}_{n}', +1) for t in THEMES] + [(f'{s}_{n}', sens) for s, sens in variables]
        for champ, sens in cles:
            vp = [(sens * f[champ], surf[f.id()]) for f in feats if f[champ] is not None]
            mins[champ] = min(v for v, w in vp)
            for q in PARTS:
                seuils[(champ, q)] = _seuil_pondere(vp, q)

    def dans_top(val, champ, sens, q):
        if val is None:
            return False
        v = sens * val
        return v >= seuils[(champ, q)] and v > mins[champ]   # les ex aequo au minimum ne comptent pas

    fidx = {nm: lyr.fields().indexOf(nm) for nm, t in nouveaux}
    changes = {}
    for f in feats:
        ch = {}
        for n in NIVS:
            for q in PARTS:
                th = [t for t in THEMES if dans_top(f[f'i_{t}_{n}'], f'i_{t}_{n}', +1, q)]
                nv = sum(1 for s, sens in variables if dans_top(f[f'{s}_{n}'], f'{s}_{n}', sens, q))
                ch[fidx[f'nth_top{q}_{n}']] = len(th)
                ch[fidx[f'nvar_top{q}_{n}']] = nv
                ch[fidx[f'th_top{q}_{n}']] = ' + '.join(NOMS_THEMES[t] for t in th) if th else 'Aucun'
        changes[f.id()] = ch
    pr.changeAttributeValues(changes)
    with open(os.path.join(BASE, 'data', 'seuils_cumuls.json'), 'w', encoding='utf-8') as fh:
        json.dump({f'{c}|top{q}': (v if not c.startswith('rrete') else -v) for (c, q), v in seuils.items()},
                  fh, ensure_ascii=False, indent=1)
    # synthese : population et surface par nombre de themes cumules
    lyr = QgsVectorLayer(f'{GPKG}|layername={couche}', couche, 'ogr')
    synth = {}
    stot = sum(surf.values())
    for n in NIVS:
        for q in PARTS:
            d = {}
            for f in lyr.getFeatures():
                k = f[f'nth_top{q}_{n}']
                a = d.setdefault(k, [0, 0.0, 0])
                a[0] += f['population'] or 0
                a[1] += f['surf_km2'] or 0
                a[2] += 1
            synth[f'top{q}_{n}'] = {k: {'pop': v[0], 'part_surf': round(100 * v[1] / stot, 1), 'communes': v[2]}
                                    for k, v in sorted(d.items())}
    with open(os.path.join(BASE, 'data', 'synthese_cumuls.json'), 'w', encoding='utf-8') as fh:
        json.dump(synth, fh, ensure_ascii=False, indent=1)
    return synth


def etape6_cumuls_agregats(niv='p27'):
    """Part de la surface et de la population cumulant >= 2 et >= 3 themes (top 30 % et top 10 %)."""
    com = QgsVectorLayer(f'{GPKG}|layername=communes_indicateurs', 'c', 'ogr')
    res = {}
    for niveau, cle in [('departement', 'code_insee_du_departement'), ('epci', 'codes_siren_des_epci')]:
        acc = {}
        for f in com.getFeatures():
            k = (f[cle] or '').split('/')[0]
            if not k or k == 'NC':
                continue
            a = acc.setdefault(k, {'s': 0.0, 'p': 0})
            s, p = f['surf_km2'] or 0.0, f['population'] or 0
            a['s'] += s
            a['p'] += p
            for q in (30, 10):
                for m in (2, 3):
                    if (f[f'nth_top{q}_{niv}'] or 0) >= m:
                        a[f's{q}_{m}'] = a.get(f's{q}_{m}', 0.0) + s
                        a[f'p{q}_{m}'] = a.get(f'p{q}_{m}', 0) + p
        lyr = QgsVectorLayer(f'{GPKG}|layername={niveau}_indicateurs', niveau, 'ogr')
        pr = lyr.dataProvider()
        champs = [f'{x}cum{m}_top{q}_{niv}' for q in (30, 10) for m in (2, 3) for x in ('surf', 'pop')]
        exist = [f.name() for f in lyr.fields()]
        pr.addAttributes([QgsField(c, QVariant.Double) for c in champs if c not in exist])
        lyr.updateFields()
        idx = {c: lyr.fields().indexOf(c) for c in champs}
        changes = {}
        for f in lyr.getFeatures():
            a = acc.get(f['code'])
            if not a:
                continue
            ch = {}
            for q in (30, 10):
                for m in (2, 3):
                    ch[idx[f'surfcum{m}_top{q}_{niv}']] = round(100 * a.get(f's{q}_{m}', 0) / a['s'], 1) if a['s'] else None
                    ch[idx[f'popcum{m}_top{q}_{niv}']] = round(100 * a.get(f'p{q}_{m}', 0) / a['p'], 1) if a['p'] else None
            changes[f.id()] = ch
        pr.changeAttributeValues(changes)
        res[niveau] = len(changes)
    return res


def etape7_parts_themes(niveaux=('p27', 'p40'), parts=(30, 10)):
    """Departements / EPCI : part (%) de la surface situee dans les q % du territoire les plus exposes,
    theme par theme -> champs pt_{theme}_top{q}_{niv} (sert aux diagrammes aux centroides)."""
    com = QgsVectorLayer(f'{GPKG}|layername=communes_indicateurs', 'c', 'ogr')
    feats = [(f['code_insee_du_departement'], (f['codes_siren_des_epci'] or '').split('/')[0], f['surf_km2'] or 0.0,
              {(n, q): f[f'th_top{q}_{n}'] or '' for n in niveaux for q in parts}) for f in com.getFeatures()]
    res = {}
    for niveau, pos in [('departement', 0), ('epci', 1)]:
        acc = {}
        for rec in feats:
            k = rec[pos]
            if not k or k == 'NC':
                continue
            a = acc.setdefault(k, {'s': 0.0})
            a['s'] += rec[2]
            for (n, q), txt in rec[3].items():
                for t, lib in NOMS_THEMES.items():
                    if lib in txt.split(' + '):
                        a[(t, q, n)] = a.get((t, q, n), 0.0) + rec[2]
        lyr = QgsVectorLayer(f'{GPKG}|layername={niveau}_indicateurs', niveau, 'ogr')
        pr = lyr.dataProvider()
        champs = [f'pt_{t}_top{q}_{n}' for n in niveaux for q in parts for t in THEMES]
        exist = [f.name() for f in lyr.fields()]
        pr.addAttributes([QgsField(c, QVariant.Double) for c in champs if c not in exist])
        lyr.updateFields()
        idx = {c: lyr.fields().indexOf(c) for c in champs}
        changes = {}
        for f in lyr.getFeatures():
            a = acc.get(f['code'])
            if not a or not a['s']:
                continue
            changes[f.id()] = {idx[f'pt_{t}_top{q}_{n}']: round(100 * a.get((t, q, n), 0.0) / a['s'], 1)
                               for n in niveaux for q in parts for t in THEMES}
        pr.changeAttributeValues(changes)
        res[niveau] = len(changes)
    return res
