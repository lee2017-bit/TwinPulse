# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Generic coverage utilities. No image-hash-specific product reference."""


def photo_reference(image_sha256):
    """Retired compatibility API: an image hash never supplies scene facts."""
    return None


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
