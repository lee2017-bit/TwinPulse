# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
import json
from pathlib import Path
import tempfile
import unittest
from scripts.verify_chat_sim_journey import copy_ordinary_settings, ROOT
from twinpulse_provider.model_contracts import load_catalog,catalog_sha


class OrdinarySettingsClosureTests(unittest.TestCase):
    def settings(self,directory,catalog=True):
        directory.mkdir()
        (directory/'provider_settings.json').write_text('{}',encoding='utf-8')
        (directory/'provider_keys.json').write_text('{"metadata_only":true}',encoding='utf-8')
        reviewed=ROOT/'outputs/benchmark-code-preparation-20261010/catalog-v401.json'
        data=json.loads(reviewed.read_text(encoding='utf-8'))
        bound=catalog_sha(data)
        (directory/'provider_stage_routing.json').write_text(json.dumps(dict(schema_version='1.0',
            route=dict(model_catalog_sha256=bound))),encoding='utf-8')
        if catalog:(directory/'stage_model_catalog.json').write_bytes(reviewed.read_bytes())
        (directory/'unreviewed-extra.json').write_text('{}',encoding='utf-8')
        return directory/'provider_settings.json',bound

    def test_catalog_closure_copies_only_reviewed_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);settings,bound=self.settings(root/'source')
            target=root/'runtime';copy_ordinary_settings(settings,target)
            self.assertEqual(len(list(target.iterdir())),4)
            self.assertFalse((target/'unreviewed-extra.json').exists())
            self.assertEqual(catalog_sha(load_catalog(target/'stage_model_catalog.json',bound)),bound)
            for path in target.iterdir():self.assertEqual(path.read_bytes(),(settings.parent/path.name).read_bytes())

    def test_missing_bound_catalog_fails_before_any_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);settings,_=self.settings(root/'source',False)
            with self.assertRaises((ValueError,OSError)):copy_ordinary_settings(settings,root/'runtime')
            self.assertFalse((root/'runtime').exists())

    def test_changed_bound_catalog_fails_before_any_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);settings,_=self.settings(root/'source')
            (settings.parent/'stage_model_catalog.json').write_text('{}',encoding='utf-8')
            with self.assertRaises(ValueError):copy_ordinary_settings(settings,root/'runtime')
            self.assertFalse((root/'runtime').exists())

    def test_legacy_route_does_not_acquire_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);settings,_=self.settings(root/'source')
            (settings.parent/'provider_stage_routing.json').write_text('{"schema_version":"1.0","route":null}',encoding='utf-8')
            copy_ordinary_settings(settings,root/'runtime')
            self.assertEqual(len(list((root/'runtime').iterdir())),3)


if __name__=='__main__':unittest.main()
