"""Reproduce Phase 2's declared ranking/text comparison and fixed website sample.

Reads owned data only. No user writes, provider calls or synthetic quality labels.
"""

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

from adventour_backend.services import local_index_service as index
from adventour_backend.services import personal_ranking_service as ranking
from adventour_backend.services import tag_group_service as tags

HERE = Path(__file__).resolve().parent
CENTERS = {'palm_coast': (29.5844,-81.2079), 'orlando': (28.5383,-81.3792)}
PROFILES = [['coffee_sweets','outdoors'], ['arts_culture','food_drink']]


def summary(places, interests):
    return {'count':len(places), 'interest_matches':sum(bool(set(p['tag_groups']) & set(interests)) for p in places),
            'mean_distance_m':round(sum(p['distance_meters'] for p in places)/max(1,len(places))),
            'duplicate_entities':len(places)-len({p['place_id'] for p in places}), 'cards':places}


def run(connection):
    result={'generated_at':datetime.now(timezone.utc).isoformat(), 'model':ranking.MODEL,
            'evidence':'Development behavior comparison, not held-out human quality evaluation',
            'ranking':{},'text':{},'website_sample':[],'closed_sample':[]}
    for metro,(lat,lon) in CENTERS.items():
        pool=connection.execute(index.SQL,{'cells':index._cells_for(lat,lon,8000),
            'floor':index.AUTHENTICITY_FLOOR,'allow_chains':False,'lat':lat,'lon':lon,'radius':8000,'user_id':0}).mappings().all()
        cards=[{'place_id':r['entity_id'],'name':r['name'],'tag_groups':tags.for_place(r['name'],index._types_for(r['basic_category'],r['taxonomy_bucket'])),
                'distance_meters':round(r['distance_meters']),'structural_score':r['authenticity'], 'chain_class':r['chain_class']} for r in pool]
        comparisons=[]
        for interests in PROFILES:
            history=ranking.from_history(interests,[],datetime.now(timezone.utc))
            personal=[ranking.score(dict(p),history,8000,p['chain_class']) for p in cards]
            personal.sort(key=lambda p:(-p['score'],p['distance_meters'],p['place_id']))
            comparisons.append({'interests':interests,'baseline':summary(cards[:10],interests),
                                'personal':summary(personal[:10],interests)})
        result['ranking'][metro]={'eligible_pool':len(cards),'profiles':comparisons}
        original=json.loads((HERE/'qa'/f'adventour_{metro}_labels.json').read_text(encoding='utf-8'))['labels']
        original=[r for r in original if r.get('label')]
        differences=[]
        for r in sorted(original,key=lambda r:r['id']):
            types=index._types_for(r.get('basic_category'),None)
            category=tags.for_place('',types); named=tags.for_place(r['name'],types)
            if named != category:
                differences.append({'id':r['id'],'name':r['name'],'category':r.get('basic_category'),
                                    'category_tags':category,'name_and_category_tags':named,
                                    'original_quality_label':r.get('label')})
        result['text'][metro]={'sample_count':len(original),'disagreement_count':len(differences),
                               'inspected_disagreements':differences[:20]}
        records=connection.execute(text("""SELECT DISTINCT ON (COALESCE(canonical_id,id))
            COALESCE(canonical_id,id) AS entity_id,id,name,websites,basic_category,metro,lat,lon
            FROM places WHERE metro=:metro AND index_active AND tier='KEEP' AND authenticity>=.30
            AND chain_class='independent' AND cardinality(websites)>0
            ORDER BY COALESCE(canonical_id,id),id"""),{'metro':metro}).mappings().all()
        ordered=sorted((dict(r) for r in records),key=lambda r:hashlib.sha256(r['entity_id'].encode()).hexdigest())
        result['website_sample'].extend(ordered[:30])
        # Original closure labels are free text; preserve matched note, don't infer
        # closure from a low-quality label or a failed HTTP request.
        for r in original:
            note=(r.get('note') or '').lower()
            if 'closed' in note or 'no longer' in note:
                found=connection.execute(text('SELECT id,name,websites,metro FROM places WHERE id=:id'),{'id':r['id']}).mappings().first()
                if found: result['closed_sample'].append({**dict(found),'human_note':r['note']})
    result['closed_sample']=sorted(result['closed_sample'],key=lambda r:r['id'])[:10]
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    engine=create_engine(dotenv_values(HERE.parent/'.env.local')['DATABASE_URL'])
    with engine.connect() as connection: report=run(connection)
    args.output.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'text':{m:{k:v for k,v in r.items() if k!='inspected_disagreements'} for m,r in report['text'].items()},
        'ranking':{m:[{'interests':r['interests'],'baseline_matches':r['baseline']['interest_matches'],
                       'personal_matches':r['personal']['interest_matches']} for r in data['profiles']] for m,data in report['ranking'].items()},
        'website_sample':len(report['website_sample']),'closed_sample':len(report['closed_sample'])}))
