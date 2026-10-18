# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Frozen model metadata contracts only; no endpoint or quality claims."""
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path
import tempfile
import unittest
from twinpulse_provider.model_contracts import (checked_catalog,catalog_sha,load_catalog,
    model_supported,catalog_prices,catalog_from_inventory)


def catalog_fixture():
    return dict(schema_version='stage-model-catalog-1.0',verified_at='2026-10-10T00:00:00+00:00',
        valid_until='2026-10-16T00:00:00+00:00',source_sha256='a'*64,models=[
            dict(model_id=name,visible=True,modalities=modalities,context_tokens=32000,
                 input_per_million='0.2',output_per_million='0.5')
            for name,modalities in (('test/vision',['text','image']),('test/planner',['text']),('test/embedding',[]))])


class ModelContractTests(unittest.TestCase):
    def test_roles_have_no_embedding_or_text_only_observer_fallback(self):
        value=checked_catalog(catalog_fixture());before=deepcopy(value)
        self.assertTrue(model_supported(value,'observer','test/vision'))
        self.assertFalse(model_supported(value,'observer','test/planner'))
        self.assertFalse(model_supported(value,'planner','test/embedding'))
        self.assertFalse(model_supported(value,'critic','test/vision'))
        self.assertNotIn('test/embedding',catalog_prices(value));self.assertEqual(value,before)

    def test_sha_price_modality_changes_and_duplicate_fields_fail_closed(self):
        value=catalog_fixture()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.json';path.write_text(json.dumps(value),encoding='utf-8')
            self.assertEqual(load_catalog(path,catalog_sha(value)),value)
            changed=deepcopy(value);changed['models'][0]['input_per_million']='5'
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'SHA_CHANGED'):load_catalog(path,catalog_sha(value))
            path.write_text('{"schema_version":"a","schema_version":"b"}',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'DUPLICATE_FIELD'):load_catalog(path,catalog_sha(value))

    def test_expired_future_or_extended_prices_do_not_gain_authority(self):
        for date in ('2026-10-09T00:00:00+00:00','2026-10-16T00:00:00+00:00'):
            with self.assertRaisesRegex(ValueError,'EXPIRED_OR_FUTURE'):
                checked_catalog(catalog_fixture(),now=datetime.fromisoformat(date))
        value=catalog_fixture();value['valid_until']='2026-10-18T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'VALIDITY_INVALID'):checked_catalog(value)

    def test_invalid_caps_prices_urls_secrets_and_ambiguous_ids_rejected(self):
        for key,val in (('input_per_million','NaN'),('output_per_million','-1'),
                        ('context_tokens',True),('model_id','https://evil.test/model'),('modalities',[{}])):
            value=catalog_fixture();value['models'][0][key]=val
            with self.assertRaises(ValueError):checked_catalog(value)
        value=catalog_fixture();value['api_key']='DO_NOT_EXPORT'
        with self.assertRaises(ValueError):checked_catalog(value)
        value=catalog_fixture();value['models'].append(deepcopy(value['models'][0]))
        with self.assertRaisesRegex(ValueError,'ID_INVALID'):checked_catalog(value)

    def test_saved_inventory_normalization_excludes_private_account_and_approval(self):
        value=catalog_fixture()
        inventory=dict(created_at=value['verified_at'],catalog_sha256='a'*64,
            authorization='PRIVATE',account_models=['PRIVATE'],models=[
                dict(provider='nebius',use_cases=r['modalities']+['reasoning'],supports=[],
                     **{k:v for k,v in r.items() if k!='modalities'}) for r in value['models']])
        result=catalog_from_inventory(inventory,valid_until=value['valid_until'])
        for row in value['models']:row['modalities'].sort()
        self.assertEqual(result,value);self.assertNotIn('PRIVATE',json.dumps(result))


if __name__=='__main__':unittest.main()
