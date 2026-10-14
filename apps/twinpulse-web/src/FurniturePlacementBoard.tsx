// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from "react";
import type { SceneEditPreview, SiteDraftSummary, WorkflowState } from "./types";
import { ApiError, TwinPulseApi } from "./api";
import type { FurnitureKind } from "./furnitureIntent";
import { OperationFeedback } from "./OperationFeedback";

export interface StagedFurniture {
  id: string;
  kind: FurnitureKind;
  x: number | null;
  y: number | null;
  yawDeg: 0 | 90 | 180 | -90;
}

const LABELS: Record<FurnitureKind, string> = {
  bed: "Bed", wardrobe: "Wardrobe", desk: "Desk", chair: "Chair", sofa: "Sofa",
  dining_table: "Dining table", storage: "Storage unit",
};
// Visual guidance only; final dimensions, rotation and collision are checked by the server.
const FOOTPRINTS: Record<FurnitureKind, [number, number]> = {
  bed: [1.4, 2.0], wardrobe: [1.2, .65], desk: [1.2, .6], chair: [.46, .45],
  sofa: [1.6, .8], dining_table: [1.4, .8], storage: [.8, .45],
};
const DIRECTIONS = [
  { yaw: 0, label: "Up (+Y)", arrow: "↑" },
  { yaw: -90, label: "Right (+X)", arrow: "→" },
  { yaw: 180, label: "Down (-Y)", arrow: "↓" },
  { yaw: 90, label: "Left (-X)", arrow: "←" },
] as const;
type CardinalYaw = StagedFurniture["yawDeg"];
function directionArrow(yaw: number): string {
  return DIRECTIONS.find((direction) => direction.yaw === yaw)?.arrow ?? "↗";
}

interface FloorRect { x: number; y: number; width: number; length: number }

function floorFromSite(site: SiteDraftSummary): FloorRect | null {
  const floor = site.objects.find((item) => item.kind === "floor" && item.shape === "box");
  if (!floor || floor.position_m.length < 2 || floor.dimensions_m.length < 2 ||
      floor.dimensions_m[0] <= 0 || floor.dimensions_m[1] <= 0) return null;
  return { x: floor.position_m[0], y: floor.position_m[1],
    width: floor.dimensions_m[0], length: floor.dimensions_m[1] };
}

function fromPointer(clientX: number, clientY: number, rect: DOMRect, floor: FloorRect): [number, number] | null {
  if (rect.width <= 0 || rect.height <= 0 || clientX < rect.left || clientX > rect.right ||
      clientY < rect.top || clientY > rect.bottom) return null;
  const x = floor.x + ((clientX - rect.left) / rect.width - .5) * floor.width;
  const y = floor.y + (.5 - (clientY - rect.top) / rect.height) * floor.length;
  return [Math.round(x * 100) / 100, Math.round(y * 100) / 100];
}

function at(x: number, y: number, floor: FloorRect, kind: FurnitureKind, yawDeg: number): CSSProperties {
  const [width, length] = FOOTPRINTS[kind];
  const angle = yawDeg * Math.PI / 180;
  const extentX = Math.abs(Math.cos(angle)) * width + Math.abs(Math.sin(angle)) * length;
  const extentY = Math.abs(Math.sin(angle)) * width + Math.abs(Math.cos(angle)) * length;
  return { left: `${50 + (x - floor.x) / floor.width * 100}%`,
    top: `${50 - (y - floor.y) / floor.length * 100}%`,
    width: `${extentX / floor.width * 100}%`, height: `${extentY / floor.length * 100}%` };
}

function errorText(caught: unknown): string {
  return caught instanceof ApiError ? `${caught.message} (${caught.code})` :
    caught instanceof TypeError && /Failed to fetch|NetworkError/i.test(caught.message)
      ? "Cannot connect to the App server. Check the connection and refresh the current saved scene before retrying." :
    caught instanceof Error ? caught.message : "Could not review the furniture placement.";
}

export function FurniturePlacementBoard({ api, site, items, onItemsChange, onApplied }: {
  api: TwinPulseApi;
  site: SiteDraftSummary;
  items: StagedFurniture[];
  onItemsChange: (items: StagedFurniture[]) => void;
  onApplied: (workflow: WorkflowState) => void;
}) {
  const floor = floorFromSite(site);
  const mapRef = useRef<HTMLDivElement>(null);
  const dragId = useRef<string | null>(null);
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const [hover, setHover] = useState<{ id: string; x: number; y: number } | null>(null);
  const [preview, setPreview] = useState<{ value: SceneEditPreview; itemsKey: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const itemsKey = JSON.stringify(items);
  const selected = items.find((item) => item.id === activeId) ?? items[0];
  const allPlaced = items.length > 0 && items.every((item) =>
    item.x !== null && item.y !== null && Number.isFinite(item.x) && Number.isFinite(item.y));

  useEffect(() => { setPreview(null); }, [site.revision, itemsKey]);
  useEffect(() => {
    if (!items.some((item) => item.id === activeId)) setActiveId(items[0]?.id ?? "");
  }, [items, activeId]);

  const updateItem = (id: string, position: [number | null, number | null]) => {
    onItemsChange(items.map((item) => item.id === id ? { ...item, x: position[0], y: position[1] } : item));
    setPreview(null); setError(null);
  };
  const updateDirection = (id: string, yawDeg: CardinalYaw) => {
    onItemsChange(items.map((item) => item.id === id ? { ...item, yawDeg } : item));
    setPreview(null); setError(null);
  };
  const pointerPosition = (event: ReactPointerEvent<HTMLElement>) => floor && mapRef.current
    ? fromPointer(event.clientX, event.clientY, mapRef.current.getBoundingClientRect(), floor) : null;
  const pointerHandlers = (id: string) => ({
    onPointerDown: (event: ReactPointerEvent<HTMLElement>) => {
      dragId.current = id; setActiveId(id);
      event.currentTarget.setPointerCapture?.(event.pointerId);
    },
    onPointerMove: (event: ReactPointerEvent<HTMLElement>) => {
      if (dragId.current !== id) return;
      const position = pointerPosition(event);
      setHover(position ? { id, x: position[0], y: position[1] } : null);
    },
    onPointerUp: (event: ReactPointerEvent<HTMLElement>) => {
      if (dragId.current !== id) return;
      const position = pointerPosition(event);
      if (position) updateItem(id, position);
      dragId.current = null; setHover(null);
    },
    onPointerCancel: () => { dragId.current = null; setHover(null); },
  });

  const previewItems = async () => {
    if (!allPlaced || !floor || site.derived_review_revision != null) return;
    setBusy(true); setBusyLabel("Validating and previewing furniture placement…"); setError(null); setPreview(null);
    try {
      const calls = items.map((item) => ({
        call_id: `edit_${crypto.randomUUID().replaceAll("-", "")}`,
        tool: "place_furniture", arguments: {
          id: item.id, kind: item.kind, catalog_version: "furniture-blocks-1.0",
          center_m: [item.x, item.y], yaw_deg: item.yawDeg,
        },
      }));
      const value = await api.previewSceneEdit(`edit_${crypto.randomUUID().replaceAll("-", "")}`,
        items.length === 1 ? "add" : "add_many", null,
        items.length === 1 ? calls[0] : { calls });
      setPreview({ value, itemsKey });
    } catch (caught) { setError(errorText(caught)); }
    finally { setBusy(false); setBusyLabel(null); }
  };
  const applyItems = async () => {
    if (!preview || preview.itemsKey !== itemsKey || preview.value.parent_revision !== site.revision) return;
    setBusy(true); setBusyLabel("Saving the reviewed furniture placement…"); setError(null);
    try {
      const next = await api.applySceneEdit(preview.value.operation, preview.value.preview_digest);
      setPreview(null); onItemsChange([]); onApplied(next);
    } catch (caught) { setPreview(null); setError(errorText(caught)); }
    finally { setBusy(false); setBusyLabel(null); }
  };
  const existing = (site.editable_calls ?? []).filter((call) => call.tool === "place_furniture")
    .flatMap((call) => {
      const kind = call.arguments.kind as FurnitureKind;
      const center = call.arguments.center_m;
      return floor && kind in FOOTPRINTS && Array.isArray(center) && center.length === 2
        ? [{ id: call.call_id, kind, x: Number(center[0]), y: Number(center[1]),
          yawDeg: Number(call.arguments.yaw_deg ?? 0) }] : [];
    });

  return <section className="furniture-placement" aria-label="Furniture staging and room placement">
    <h4>Staged furniture · {items.length}</h4>
    <p>Drag furniture onto the room floor, or select an item and then click the floor. Set each item's facing to up, right, down, or left. X/Y inputs also work on mobile and with a keyboard.</p>
    <div className="furniture-placement-layout">
      <div className="furniture-tray" aria-label="Unplaced furniture tray">
        {items.map((item) => <button key={item.id} type="button" className={item.id === activeId ? "active" : ""}
          aria-label={`${LABELS[item.kind]} staged item`} onClick={() => setActiveId(item.id)} {...pointerHandlers(item.id)}>
          {directionArrow(item.yawDeg)} {LABELS[item.kind]} · {item.x === null || item.y === null ? "not placed" : `${item.x.toFixed(2)}, ${item.y.toFixed(2)} m`}
        </button>)}
      </div>
      {floor ? <div ref={mapRef} className="furniture-room-map" aria-label="Room floor placement map"
        style={{ aspectRatio: `${floor.width} / ${floor.length}` }}
        onClick={(event) => {
          if (!selected) return;
          const position = fromPointer(event.clientX, event.clientY, event.currentTarget.getBoundingClientRect(), floor);
          if (position) updateItem(selected.id, position);
        }}>
        <span className="room-map-back">+Y · back</span>
        {existing.map((item) => <span key={item.id} className="room-map-existing"
          style={at(item.x, item.y, floor, item.kind, item.yawDeg)}>{LABELS[item.kind]}</span>)}
        {items.map((item) => {
          const position = hover?.id === item.id ? { x: hover.x, y: hover.y } :
            item.x !== null && item.y !== null ? { x: item.x, y: item.y } : null;
          return position && <button key={item.id} type="button" className="room-map-staged"
            aria-label={`${LABELS[item.kind]} placed position`} style={at(position.x, position.y, floor, item.kind, item.yawDeg)}
            onClick={(event) => { event.stopPropagation(); setActiveId(item.id); }} {...pointerHandlers(item.id)}>
            {directionArrow(item.yawDeg)} {LABELS[item.kind]}
          </button>;
        })}
        <span className="room-map-front">-Y · front</span>
      </div> : <p role="alert">The floor dimensions are unavailable; floor placement is disabled.</p>}
    </div>
    {selected && <div className="furniture-position-fields">
      <strong>{LABELS[selected.kind]} position · metres from room center</strong>
      <label>X (m)<input aria-label="Staged X (m)" type="number" step="0.01" value={selected.x ?? ""}
        onChange={(event) => updateItem(selected.id, [event.target.value === "" ? null : Number(event.target.value), selected.y])} /></label>
      <label>Y (m)<input aria-label="Staged Y (m)" type="number" step="0.01" value={selected.y ?? ""}
        onChange={(event) => updateItem(selected.id, [selected.x, event.target.value === "" ? null : Number(event.target.value)])} /></label>
      <label>Facing<select aria-label="Staged direction" value={selected.yawDeg}
        onChange={(event) => updateDirection(selected.id, Number(event.target.value) as CardinalYaw)}>
        {DIRECTIONS.map((direction) => <option key={direction.yaw} value={direction.yaw}>{direction.arrow} {direction.label}</option>)}
      </select></label>
      <button type="button" onClick={() => updateItem(selected.id, [null, null])}>Clear this placement</button>
    </div>}
    <p>Facing follows this floor map's X/Y axes; it is not automatically aligned to the photo's window. The map is an approximate placement guide. The server preview checks rotated walls, overlap, and object limits. Staging does not change the source or 3D scene.</p>
    <div className="action-row">
      <button type="button" disabled={!allPlaced || !floor || busy || site.derived_review_revision != null}
        onClick={() => void previewItems()}>Preview all</button>
      <button type="button" className="primary" disabled={busy || !preview || preview.itemsKey !== itemsKey ||
        preview.value.parent_revision !== site.revision} onClick={() => void applyItems()}>Save reviewed furniture</button>
      <button type="button" disabled={busy} onClick={() => { onItemsChange([]); setPreview(null); }}>Cancel staging</button>
    </div>
    {preview && <div role="status"><p>This revision adds {items.length} furniture items and {Object.keys(preview.value.affected_after).length} parts. {preview.value.preserved_object_count} existing objects stay unchanged. Physical validation was not run.</p>
      <div className="table-wrap"><table><thead><tr><th>Added part</th><th>Center position (m)</th></tr></thead><tbody>
        {Object.entries(preview.value.affected_after).map(([id, item]) => <tr key={id}><td>{id}</td>
          <td>{item.position_m.map((value) => value.toFixed(2)).join(" / ")}</td></tr>)}
      </tbody></table></div>
    </div>}
    <OperationFeedback busyLabel={busyLabel} error={error} onDismiss={() => setError(null)} />
  </section>;
}
