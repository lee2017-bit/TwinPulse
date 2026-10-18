# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit synthetic layout for product wiring, never photo interpretation."""
from twinpulse_core.model_library import library_models, FURNITURE_MODELS
from twinpulse_provider.photo_layout import SIZES, PARAMETRIC_REVISION


def object_intent(identity,kind,region,*,size=None,parent=None,part=None,relation='floor'):
    model=next(m for m in library_models() if m['kind']==kind)
    dimensions=list(size or (FURNITURE_MODELS[kind][0] if kind in FURNITURE_MODELS else SIZES[kind]))
    return dict(id=identity,kind=kind,region=region,yaw_deg=0,observation_ids=['bed_visual'],
        model_id=model['model_id'],dimensions_m=dimensions,variant=model['variants'][0],
        finish=model['finishes'][0],placement=dict(relation=relation,parent_id=parent,
            part=part,anchor='centre',elevation_m=None))


def intent(*objects,width=4,length=5):
    return dict(layout_version=PARAMETRIC_REVISION,summary='Synthetic estimated library layout, not reconstructed.',
        room=dict(width_m=width,length_m=length,height_m=2.6),objects=list(objects))
