"""Replay frozen offline weights over explicitly manual evidence labels."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = 'c6ce681b418d10ceca06f18cfd64d3ace1fae8718725e3b46a97430aab390f6a'
protocol_bytes = (ROOT / 'protocol.json').read_bytes().replace(b'\r\n', b'\n')
assert hashlib.sha256(protocol_bytes).hexdigest() == EXPECTED, 'Frozen protocol changed'
protocol = json.loads(protocol_bytes)
labels = json.loads((ROOT / 'labels.json').read_text(encoding='utf-8'))
weights = protocol['score_0_100']


def score(row):
    parts = {
        'coffee': weights['coffee_centered_activity'] * int(row['coffee']),
        'cafe': weights['verified_coffee_serving_cafe_setting'] * int(row['cafe']),
        'social': weights['explicit_social_or_participatory_activity'] * int(row['social']),
    }
    return {'title': row['title'], 'origin': row['origin'], 'start': row['start'],
            'points': parts, 'fit': sum(parts.values()) if row['eligible'] else None,
            'url': row['url']}


ranked = [score(row) for row in labels['candidates'] if row['eligible']]
ranked.sort(key=lambda row: (-row['fit'], row['start'], row['title']))
parks_ranked = sorted((score(row) for row in labels['parks_candidates']),
                      key=lambda row: (-row['fit'], row['start'], row['title']))
result = {'protocol_sha256': EXPECTED, 'fixed_search_ranked': ranked,
          'parks_date_override_ranked': parks_ranked,
          'separate_user_supplied_diagnostic': score(labels['user_supplied_diagnostic']),
          'warning': 'Manual labels and experimental relevance points; no production personalization or organic discovery claim.'}
(ROOT / 'scores.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
