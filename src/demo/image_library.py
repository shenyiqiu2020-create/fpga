"""Allowlisted received test crops shared by the browser and inference route."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

SET_NAMES = {
    'historical_development_48': '早期开发集',
    'historical_holdout_33_accepted': '早期留出集',
    'expanded_development_155': '扩批开发集',
    'expanded_holdout_48': '扩批留出集',
}


class ImageLibrary:
    def __init__(self, root):
        self.root = Path(root).resolve()
        allowed = (self.root / 'data/test_inputs').resolve()
        manifest = json.loads((allowed / 'evaluation_manifest.json').read_text(encoding='utf-8'))
        self.images = []
        self.paths = {}
        for row in manifest['images']:
            source = (self.root / row['path']).resolve()
            if not source.is_relative_to(allowed) or source.suffix.lower() != '.png' or not source.is_file():
                raise ValueError('Invalid test-image path: ' + row['path'])
            if row['set'] not in SET_NAMES or row['label'] not in ('good', 'defect'):
                raise ValueError('Invalid test-image metadata')
            key = sha256(row['path'].encode('utf-8')).hexdigest()[:20]
            if key in self.paths:
                raise ValueError('Duplicate test-image identity')
            self.paths[key] = source
            self.images.append({
                'id': key, 'name': row['image'], 'set': row['set'],
                'set_name': SET_NAMES[row['set']], 'label': row['label'],
                'object_group': row['object_group'],
                'calibration_group': bool(row.get('calibration_group', False)),
                'sha256': row['sha256'], 'url': '/test-images/' + key + '.png',
            })
        self.by_id = {row['id']: row for row in self.images}
        counts = Counter(row['set'] for row in self.images)
        self.public = {
            'total': len(self.images),
            'unique_images': len({row['sha256'] for row in self.images}),
            'sets': [{'id': key, 'name': name, 'count': counts[key]} for key, name in SET_NAMES.items()],
            'images': self.images,
        }

    def source(self, key):
        return self.paths.get(key)
