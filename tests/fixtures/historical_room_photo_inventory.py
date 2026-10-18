# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
# Archived v349 test reference. NEVER import from product generation code.
"""Human-reviewed supplied-photo inventory. No coordinates inferred or robot authority."""
PHOTO_SHA256 = 'ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8'
# id, English label, supported category, visibility, floor-risk coverage required.
PHOTO_ITEMS = (
    ('bed', 'Bed including base and mattress', 'bed', 'visible', True),
    ('wardrobe', 'Wardrobe body', 'wardrobe', 'visible', True),
    ('desk', 'Desk including legs', 'desk', 'visible', True),
    ('office_chair', 'Rolling office chair including wheel base', 'office_chair', 'visible', True),
    ('wood_frame', 'Wooden frame or clothes rack', 'clothes_rack', 'uncertain_identity', True),
    ('floor_fan', 'Floor fan including stand and base', 'floor_fan', 'partly_occluded', True),
    ('entry_door', 'Entry door leaf and current opening', 'door_leaf', 'visible', True),
    ('wardrobe_door', 'Open wardrobe door leaf', 'door_leaf', 'visible', True),
    ('hanging_clothes', 'Hanging clothing and loose lower edges', 'hanging_clothes', 'visible', True),
    ('clothing_pile', 'Clothing lying on the floor', 'clothing_pile', 'visible', True),
    ('bedding_overhang', 'Bedding overhanging the bed', 'bedding_overhang', 'visible', True),
    ('floor_bags', 'Bags along the left floor edge', 'bag', 'partly_occluded', True),
    ('underdesk_bag', 'Bag or soft item near the chair and desk', 'bag', 'uncertain_identity', True),
    ('boxes', 'Boxes near the entry and left edge', 'box', 'visible', True),
    ('basket', 'Basket or storage container and contents', 'basket', 'visible', True),
    ('cables', 'Loose floor cable bundle', 'cable_bundle', 'visible', True),
    ('power_adapter', 'Floor power adapter', 'power_adapter', 'visible', True),
    ('power_strip', 'Floor power equipment possibly a power strip', 'power_strip', 'uncertain_identity', True),
    ('small_equipment', 'Unidentified small floor equipment or parts', 'unknown', 'uncertain_identity', True),
    ('monitor', 'Desk display or electronic device', 'monitor', 'partly_occluded', False),
    ('tabletop_items', 'Desk electronics and small items', 'tabletop_item', 'partly_occluded', False),
    ('window_blind', 'Window and blind', 'window_blind', 'visible', False),
    ('ceiling_light', 'Ceiling light', 'ceiling_light', 'partly_occluded', False),
    ('top_storage', 'Storage box above the wardrobe', 'box', 'visible', False),
)


def photo_reference(image_sha256):
    if image_sha256 != PHOTO_SHA256:
        return None
    return dict(schema_version='photo-room-inventory-1.0', image_sha256=PHOTO_SHA256,
        source='human_review_of_user_photo', capture_time_utc=None, live_observation=False,
        geometry_status='UNMEASURED', physical_validation='NOT_RUN',
        items=[dict(id=i, label=label, kind=kind, visibility=visibility, required_for_route=required,
                    position_m=None, dimensions_m=None, placement_status='unplaced')
               for i, label, kind, visibility, required in PHOTO_ITEMS])


def inventory_coverage(reference, represented):
    if reference is None:
        return None
    by_id = {item['id']: item for item in represented['items']} if represented else {}
    rows = []
    for original in reference['items']:
        item = by_id.get(original['id'])
        # An unrelated same-id object is not coverage of the observed category.
        valid = item and item['kind'] == original['kind'] and item['placement_status'] == 'represented'
        rows.append({**original, 'placement_status': 'represented' if valid else 'unplaced',
                     'geometry': item['geometry'] if valid else [],
                     'last_observation_utc': item['last_observation_utc'] if valid else None})
    missing = [r['id'] for r in rows if r['required_for_route'] and r['placement_status'] != 'represented']
    return {**reference, 'items': rows, 'missing_route_items': missing, 'route_inventory_complete': not missing}

