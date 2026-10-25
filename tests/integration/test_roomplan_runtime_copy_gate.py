# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from scripts.roomplan_runtime_copy_gate import check_runtime_copy,REQUIRED,OPTIONAL

class RuntimeCopyGateTests(unittest.TestCase):
    def test_exact_and_optional_missing_and_reject_tampering(self):
        with TemporaryDirectory() as directory:
            folder=Path(directory);kit='kit_20261023_123456.log';rows=[]
            for name in sorted(REQUIRED|{OPTIONAL,kit}):
                raw=name.encode();(folder/name).write_bytes(raw)
                rows.append(dict(name=name,status='EXACT_COPY',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
            value=dict(launch_id='launch',kit_log='C:/isaacsim/kit/logs/Kit/Isaac-Sim Python/6.0/'+kit,files=rows)
            self.assertEqual(check_runtime_copy(folder,'launch',value),[])
            absent=deepcopy(value)
            absent['files']=[dict(name=OPTIONAL,status='ORIGINAL_UNAVAILABLE') if x['name']==OPTIONAL else x for x in rows]
            self.assertTrue(check_runtime_copy(folder,'launch',absent))  # Existing file cannot be called unavailable.
            (folder/OPTIONAL).unlink()
            self.assertEqual(check_runtime_copy(folder,'launch',absent),[])
            for change in ('empty','missing','duplicate','extra','traversal','hash','size','launch','kit','unavailable_required'):
                bad=deepcopy(absent)
                if change=='empty':bad['files']=[]
                if change=='missing':bad['files']=bad['files'][1:]
                if change=='duplicate':bad['files'].append(deepcopy(bad['files'][0]))
                if change in {'extra','traversal'}:bad['files'].append(dict(name='../outside' if change=='traversal' else 'unexpected.log',status='EXACT_COPY'))
                if change=='hash':bad['files'][0]['sha256']='0'*64
                if change=='size':bad['files'][0]['bytes']=0
                if change=='launch':bad['launch_id']='other'
                if change=='kit':bad['kit_log']='C:/other/'+kit
                if change=='unavailable_required':bad['files'][0]={'name':bad['files'][0]['name'],'status':'ORIGINAL_UNAVAILABLE'}
                with self.subTest(change=change):self.assertTrue(check_runtime_copy(folder,'launch',bad))

if __name__=='__main__':unittest.main()
