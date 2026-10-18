# SPDX-License-Identifier: Apache-2.0
"""Pure read-only field evidence resolution. No control authority is restored."""
from copy import deepcopy
import hashlib
import json
import re


def restored_field_trials(raw, acknowledgements, *, writer_complete, context, writer_receipt=None, stop_raw=None):
    value=json.loads(raw)
    if value.get('context')!=context:raise ValueError('FIELD_EVIDENCE_CONTEXT_CHANGED')
    matches=[];entries=[];valid=writer_complete is True and isinstance(writer_receipt,dict)
    if valid:
        for index,line in enumerate(acknowledgements.splitlines(),1):
            ack=json.loads(line)
            if (ack.get('writer_id')!=writer_receipt.get('writer_id')
                    or not re.fullmatch('[a-f0-9]{32}',str(ack.get('writer_id','')))
                    or type(ack.get('write_id')) is not int or ack['write_id']!=index
                    or ack.get('state')!='COMMITTED' or not re.fullmatch('[a-f0-9]{64}',str(ack.get('sha256','')))):
                valid=False;break
            entries.append(ack)
            if (ack.get('state')=='COMMITTED' and ack.get('name')=='field-trials.json'
                    and ack.get('sha256')==hashlib.sha256(raw).hexdigest()):matches.append(ack)
        valid=valid and len(entries)==writer_receipt.get('last_write_id')
    trials=deepcopy(value['trials'])
    for trial in trials:
        if trial.get('status')!='PENDING_PERSISTENCE':continue
        matched=valid and bool(matches)
        if matched and trial.get('case')=='bootstrap_stop' and trial['decision']['status']=='PASS':
            receipt=trial.get('result',{}).get('receipt')
            exact=json.dumps(receipt,sort_keys=True,allow_nan=False).encode()
            matched=stop_raw==exact and any(ack.get('name')=='field-stop.json'
                and ack['write_id']<matches[-1]['write_id'] and ack['sha256']==hashlib.sha256(exact).hexdigest() for ack in entries)
        if matched:
            trial.update(**trial['decision'],persistence=dict(state='COMMITTED',writes=[matches[-1]],restored_read_only=True))
        else:trial.update(status='INCONCLUSIVE',reason='FIELD_EVIDENCE_ACK_UNCONFIRMED',persistence=dict(state='UNCONFIRMED'))
    return trials
