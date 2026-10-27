# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Dependency-free pinned room prop inventory for schema and deterministic geometry."""
ROOM_ITEM_CATALOG_VERSION = 'room-items-1.0'
ROOM_ITEM_ADDITIONS_VERSION = 'room-items-1.1'
ROOM_SURFACE_COVER_VERSION = 'room-items-1.2'
ROOM_FLOOR_LAMP_VERSION = 'room-items-1.3'  # 2026-10-27: a photographed floor lamp only fitted small_equipment (a 0.3 m cube)
WALL_ITEMS = ('window_blind', 'wall_fixture', 'wall_storage')
CEILING_ITEMS = ('ceiling_light', 'ceiling_fixture')
ADDITIONAL_ROOM_ITEMS = ('floor_covering', 'wall_fixture', 'ceiling_fixture', 'wall_storage')
REQUIRED_ROOM_RELATIONS = dict(floor_covering='floor',wall_fixture='wall',ceiling_fixture='ceiling',wall_storage='wall')
REQUIRED_ROOM_RELATIONS['surface_covering']='surface'
REQUIRED_ROOM_RELATIONS['floor_lamp']='floor'  # 2026-10-27: stands on the floor like floor_fan; a lamp on a desk is tabletop_item
BOX = ((0, 0, .5, 1, 1, 1),)
PARTS = {
    'office_chair': ((0, 0, .08, 1, 1, .12), (0, 0, .28, .12, .12, .35),
                     (0, 0, .5, .75, .75, .12), (0, .32, .77, .75, .12, .46)),
    'floor_fan': ((0, 0, .04, 1, 1, .08), (0, 0, .32, .12, .12, .55),
                  (0, 0, .77, .9, .3, .46)),
    'clothes_rack': ((-.44, 0, .5, .12, .8, 1), (.44, 0, .5, .12, .8, 1),
                     (0, 0, .92, .88, .12, .12)),
    **{kind: BOX for kind in ('door_leaf', 'bag', 'box', 'basket', 'clothing_pile',
       'hanging_clothes', 'bedding_overhang', 'cable_bundle', 'power_adapter',
       'power_strip', 'small_equipment', 'monitor', 'tabletop_item', 'window_blind',
       'ceiling_light', 'unknown', 'pallet')},
    'floor_covering': BOX,
    'surface_covering': BOX,
    'wall_fixture': BOX,
    'ceiling_fixture': BOX,
    'wall_storage': ((-.475, 0, .5, .05, 1, 1), (.475, 0, .5, .05, 1, 1),
                     (0, .475, .5, .9, .05, 1), (0, 0, .025, .9, 1, .05),
                     (0, 0, .975, .9, 1, .05), (0, 0, .5, .9, .95, .04)),
    'floor_lamp': ((0, 0, .02, 1, 1, .04), (0, 0, .44, .1, .1, .8), (0, 0, .92, 1, 1, .16)),  # base disc, pole, shade
}
ROOM_ITEM_KINDS = tuple(PARTS)


def room_item_catalog_version(kind):
    if kind=='surface_covering':return ROOM_SURFACE_COVER_VERSION
    if kind=='floor_lamp':return ROOM_FLOOR_LAMP_VERSION
    return ROOM_ITEM_ADDITIONS_VERSION if kind in ADDITIONAL_ROOM_ITEMS else ROOM_ITEM_CATALOG_VERSION
