// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type {RoomInventoryState, PhotoRoomInventory} from './types';

export function RoomInventory({inventory, photo, edit}: {inventory?: RoomInventoryState; photo?: PhotoRoomInventory|null; edit?:()=>void}) {
  if (!photo && !inventory?.items.length) return null;
  const represented = new Map(inventory?.items.map(item=>[item.id,item]) ?? []);
  const rows = photo ? [...photo.items.map(item=>({...item, represented: item.placement_status==='represented' ? represented.get(item.id) : undefined})),
    ...(inventory?.items.filter(item=>!photo.items.some(ref=>ref.id===item.id)).map(item=>({...item,represented:item})) ?? [])]
    : (inventory?.items ?? []).map(item=>({...item,represented:item}));
  return <details className="room-inventory"><summary>Room inventory · {rows.length} items</summary>
    <p>Saved proposal, not a live scan. Dimensions and placement are unverified.</p>
    {photo && !photo.route_inventory_complete && <p className="room-inventory-warning" role="status">
      {photo.missing_route_items.length} photo hazards still need placement. SIM route preparation is blocked.</p>}
    <p>Orange volumes are synthetic keepout areas for fabric, cables or unknown objects — not measured objects.</p>
    {edit && <button type="button" onClick={edit}>Edit inventory placement</button>}
    <ul>{rows.map(row=><li key={row.id}><strong>{row.label}</strong>
      <span>{row.represented ? `${row.represented.risk.replace('_',' ')} · represented` : 'Unplaced · do not assume clear space'}</span>
      <details><summary>Geometry and evidence</summary>
        <p>Category: {row.kind} · Evidence: {row.represented?.basis ?? 'human photo review'}
          {' · '}Last observation: {row.represented?.last_observation_utc ?? 'unknown'}</p>
        {row.represented?.geometry.map(g=><p key={g.id}>{g.synthetic_keepout?'Keepout':'Visual part'}: position {g.position_m.map(n=>n.toFixed(2)).join(', ')} m
          {' · '}size {g.dimensions_m.map(n=>n.toFixed(2)).join(' × ')} m · yaw {g.yaw_deg.toFixed(1)}°</p>)}
        {!row.represented && <p>No position or size has been supplied.</p>}
      </details></li>)}</ul>
  </details>;
}
