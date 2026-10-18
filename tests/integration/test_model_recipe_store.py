# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Supplementary immutable local catalog storage; not a user-flow substitute."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from twinpulse_app.model_recipe_store import ModelRecipeStore
from twinpulse_core.model_recipe import RECIPE_VERSION,INTERPRETER_VERSION


def recipe():
    return dict(schema_version=RECIPE_VERSION,interpreter_version=INTERPRETER_VERSION,title='Simple stool frame',family='home',kind='chair',
        parameters=[dict(name=n,type='number',minimum=.4,maximum=1.,default=.5) for n in ('width','depth','height')],
        parts=[dict(id='base',center=[0,0,dict(op='mul',args=['height',.5])],size=['width','depth','height'],
            material='wood',support_top=False,repeat=None)])


class RecipeStoreTests(unittest.TestCase):
    def test_atomic_immutable_dedup_and_restart(self):
        with TemporaryDirectory() as directory:
            store=ModelRecipeStore(directory);original=recipe()
            first=store.register(original,request_id='first',model_id='Nemotron')
            second=store.register(original,request_id='duplicate',model_id='Nemotron')
            self.assertEqual(first['model_id'],second['model_id'])
            newer=deepcopy(original);newer['title']='New immutable design'
            store.register(newer,request_id='next',model_id='Nemotron')
            reopened=ModelRecipeStore(directory);saved=reopened.snapshots()
            self.assertEqual(len(saved),2);self.assertEqual(saved[first['model_id']],original)
            public=reopened.public();self.assertEqual(len([m for m in public['models'] if m['origin']=='model_generated']),2)
            self.assertFalse(public['physical_authority'])
            self.assertNotIn('recipe',public['models'][-1])
            self.assertEqual(len(list((Path(directory)/'model-library').glob('*.tmp'))),0)

    def test_invalid_record_not_silently_reused(self):
        with TemporaryDirectory() as directory:
            store=ModelRecipeStore(directory);good=recipe();store.register(good,request_id='first',model_id='Nemotron')
            invalid=deepcopy(good);invalid['parts'][0]['size'][0]=0
            with self.assertRaises(ValueError):store.register(invalid,request_id='bad',model_id='Nemotron')
            self.assertEqual(len(store.snapshots()),1)


if __name__=='__main__':unittest.main()
