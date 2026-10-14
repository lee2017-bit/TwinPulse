# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Owned idle photo correction. No source waiver or device authority."""
from copy import deepcopy
import json
from pathlib import Path
import threading
from twinpulse_core.revisions import canonical_sha256
from twinpulse_core.automatic_photo_alignment import structural_section
from twinpulse_core.room_localization import segment_distance
from twinpulse_core.observed_mission import checked_goal
from .automatic_photo_store import _wall_change


class MissionSourceGuard:
    def __init__(self, fingerprint, ledger):
        self.fingerprint=fingerprint;self.ledger=Path(ledger);self.lock=threading.RLock()
        self.before=fingerprint()

    def __call__(self):
        with self.lock:
            if self.fingerprint()!=self.before:raise ValueError('MISSION_ROOM_OR_LEDGER_CHANGED')

    def append_owned(self, append):
        # Only the single immutable record returned by this owned transaction
        # can advance the snapshot. Concurrent image/recipe/existing-ledger
        # edits remain a failure, even if the append itself succeeded.
        with self.lock:
            self();event=append();after=self.fingerprint()
            prior={row[0]:row for row in self.before};current={row[0]:row for row in after}
            added=set(current)-set(prior)
            if len(added)!=1 or any(current.get(p)!=row for p,row in prior.items()):
                raise ValueError('MISSION_SOURCE_CHANGED_DURING_CORRECTION')
            path=Path(next(iter(added)))
            if path.parent!=self.ledger or path.is_symlink() or json.loads(path.read_text(encoding='utf-8'))!=event:
                raise ValueError('MISSION_CORRECTION_APPEND_NOT_OWNED')
            self.before=after
            return event


def corrected_effective_objects(effective,nominal,result,goal):
    if (result.get('policy')!='correct_walls' or result.get('status')!='ALIGNMENT_CANDIDATE'
            or result.get('geometry_status')!='BOUNDED_WALL_PROPOSAL_VALIDATED'
            or result.get('scene_revision_before')!=canonical_sha256(nominal['objects'])
            or result.get('source_map_revision') is None):
        raise ValueError('MISSION_CORRECTION_PROPOSAL_NOT_VALIDATED')
    corrected=result.get('corrected_objects')
    if not isinstance(corrected,list) or canonical_sha256(corrected)!=result.get('scene_revision_after'):
        raise ValueError('MISSION_CORRECTION_PROPOSAL_HASH')
    _wall_change(nominal['objects'],corrected)
    by_id={obj['id']:obj for obj in corrected};before=deepcopy(effective['objects']);after=deepcopy(before)
    originals={obj['id']:obj for obj in nominal['objects']}
    for obj in after:
        candidate=by_id.get(obj['id'])
        if candidate is not None and candidate!=originals[obj['id']]:
            obj['transform']['position_m'][:2]=candidate['transform']['position_m'][:2]
    _wall_change(before,after)
    section=structural_section(after,nominal['height_m']);xy=goal['xy'];bounds=section['bounds']
    # The existing conservative0.18 m guard envelope is retained. Furniture
    # lower geometry remains unknown; fresh observed-space replanning is still
    # required after this nominal structural check, not authorized by it.
    if goal['mode']!='SURVEY_ONLY' and (not bounds[0]+.18<=xy[0]<=bounds[1]-.18 or not bounds[2]+.18<=xy[1]<=bounds[3]-.18):
        raise ValueError('MISSION_CORRECTED_GOAL_OUTSIDE_FLOOR')
    if goal['mode']!='SURVEY_ONLY' and any(segment_distance(xy,[w['a'],w['b']])-w['thickness']/2<=.18 for w in section['walls']):
        raise ValueError('MISSION_CORRECTED_GOAL_IN_WALL')
    rebound=checked_goal({**goal,'room_revision':canonical_sha256(after)})
    return after,rebound
