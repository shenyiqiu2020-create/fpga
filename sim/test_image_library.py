"""Exercise the real image inventory and rejection of untrusted file paths."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/demo'))
from image_library import ImageLibrary


class ImageLibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library = ImageLibrary(ROOT)

    def test_all_four_groups_retained(self):
        self.assertEqual(self.library.public['total'], 284)
        self.assertEqual(self.library.public['unique_images'], 224)
        self.assertEqual({s['id']: s['count'] for s in self.library.public['sets']}, {
            'historical_development_48': 48, 'historical_holdout_33_accepted': 33,
            'expanded_development_155': 155, 'expanded_holdout_48': 48,
        })

    def test_every_image_is_exact_manifest_file(self):
        for row in self.library.images:
            p = self.library.source(row['id'])
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), row['sha256'])
            self.assertEqual(row['url'], '/test-images/'+row['id']+'.png')

    def test_ids_keep_repeated_group_records_separate(self):
        self.assertEqual(len(self.library.by_id), 284)
        same = Counter(x['sha256'] for x in self.library.images)
        self.assertGreater(max(same.values()), 1)
        self.assertEqual(Counter(x['label'] for x in self.library.images), {'good': 63, 'defect': 221})

    def test_unknown_ids_cannot_read_paths(self):
        for key in ['../models/student_final.pth', '0'*20, '/etc/passwd', '..\\..\\.git\\config']:
            self.assertIsNone(self.library.source(key))

    def test_manifest_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'data/test_inputs').mkdir(parents=True)
            (root/'secret.png').write_bytes(b'not a public test image')
            row = {'path':'secret.png','set':'expanded_holdout_48','label':'good'}
            (root/'data/test_inputs/evaluation_manifest.json').write_text(json.dumps({'images':[row]}))
            with self.assertRaisesRegex(ValueError, 'Invalid test-image path'):
                ImageLibrary(root)


if __name__ == '__main__':
    unittest.main(verbosity=2)
