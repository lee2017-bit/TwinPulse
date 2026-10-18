// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type { SiteDraftSummary } from "./types";

export const FURNITURE_KINDS = ["bed", "wardrobe", "desk", "chair", "sofa", "dining_table", "storage"] as const;
export type FurnitureKind = (typeof FURNITURE_KINDS)[number];

const LABELS: Record<FurnitureKind, string> = {
  bed: "bed", wardrobe: "wardrobe", desk: "desk", chair: "chair", sofa: "sofa",
  dining_table: "dining table", storage: "storage unit",
};

const ALIASES: Record<FurnitureKind, readonly string[]> = {
  bed: ["침대", "bed"], wardrobe: ["옷장", "wardrobe"], desk: ["책상", "desk"],
  chair: ["의자", "chair"], sofa: ["소파", "sofa"], dining_table: ["식탁", "dining table"],
  storage: ["수납장", "storage"],
};

export type FurnitureIntent =
  | { status: "proposal"; mode: "add_furniture" | "change_furniture"; kind: FurnitureKind;
      targetCallId: string | null; x: number | null; y: number | null; explanation: string }
  | { status: "staging"; kinds: FurnitureKind[]; explanation: string }
  | { status: "clarify"; explanation: string };

function mentions(text: string, word: string): boolean {
  return /[a-z]/i.test(word)
    ? new RegExp(`\\b${word.replaceAll(" ", "\\s+")}\\b`, "i").test(text)
    : text.includes(word);
}

function coordinate(text: string, axis: "x" | "y"): number | null {
  const found = text.match(new RegExp(`\\b${axis}\\s*(?:=|:)\\s*(-?\\d+(?:\\.\\d+)?)\\b`, "i"));
  return found ? Number(found[1]) : null;
}

/** Offline, deliberately narrow intent proposal. Never produces an apply command. */
export function interpretFurnitureIntent(
  request: string, calls: NonNullable<SiteDraftSummary["editable_calls"]>, selectedCallId = "",
): FurnitureIntent {
  const text = request.trim();
  if (!text || text.length > 200) return { status: "clarify", explanation: "Enter a request of up to 200 characters." };
  const referencesSelection = /선택한|선택된|\bselected\b/i.test(text);
  const selectedCall = calls.find((call) => call.tool === "place_furniture" && call.call_id === selectedCallId);
  const selectedKind = selectedCall && FURNITURE_KINDS.includes(selectedCall.arguments.kind as FurnitureKind)
    ? selectedCall.arguments.kind as FurnitureKind : null;
  const namedKinds = FURNITURE_KINDS.filter((kind) => ALIASES[kind].some((word) => mentions(text, word)));
  if (referencesSelection && !selectedKind) return { status: "clarify", explanation: "Select an item from the saved scene before referring to selected furniture." };
  if (referencesSelection && namedKinds.length && !namedKinds.includes(selectedKind!)) return {
    status: "clarify", explanation: "The selected furniture does not match the type named in the request. Select the correct item.",
  };
  const kinds = namedKinds.length ? namedKinds : selectedKind && referencesSelection ? [selectedKind] : [];
  if (!kinds.length) return { status: "clarify", explanation: "Specify a furniture type: bed, wardrobe, desk, chair, sofa, dining table, or storage unit." };
  const add = /추가|놓아|배치|\badd\b|\bplace\b/i.test(text);
  const move = /이동|옮겨|\bmove\b/i.test(text);
  if (add === move || /삭제|제거|지워|\bdelete\b|\bremove\b/i.test(text)) {
    return { status: "clarify", explanation: "Use one Add or Move action per request. Delete and combined actions are not supported." };
  }
  if (add && referencesSelection) return {
    status: "clarify", explanation: "Add cannot target existing selected furniture. Choose either a new item to add or the selected item to move.",
  };
  if (kinds.length > 1) {
    if (!add || kinds.length > 3) return { status: "clarify", explanation: "Move one item at a time, or stage up to three furniture types for addition." };
    return { status: "staging", kinds,
      explanation: `Add ${kinds.map((kind) => LABELS[kind]).join(', ')}. Drag each item from staging onto the room floor. No position was inferred from the photo. Preview and save them together after placement.`,
    };
  }
  const kind = kinds[0];
  const x = coordinate(text, "x");
  const y = coordinate(text, "y");
  if (add) {
    if ((x === null) !== (y === null)) return {
      status: "clarify", explanation: "For a new item, provide both X and Y coordinates, or leave both blank and place it on the floor map.",
    };
    if (x === null) return { status: "staging", kinds: [kind],
      explanation: `Add a ${LABELS[kind]}. Place it from staging on the room floor. No position was inferred from the photo or saved.`,
    };
    return { status: "proposal", mode: "add_furniture", kind, targetCallId: null, x, y,
      explanation: `Add a ${LABELS[kind]} using only the local furniture-blocks-1.0 preset. No position was inferred from the photo or external data. ${x === null ? "Enter X/Y coordinates, then" : "Check the displayed X/Y coordinates, then"} review the preview. Nothing has been saved.`,
    };
  }
  const candidates = calls.filter((call) => call.tool === "place_furniture" && call.arguments.kind === kind);
  const selected = candidates.find((call) => call.call_id === selectedCallId);
  if (referencesSelection && !selected) return {
    status: "clarify", explanation: `To move the selected ${LABELS[kind]}, first select it from the existing furniture list below.`,
  };
  const target = selected ?? (candidates.length === 1 ? candidates[0] : null);
  if (!target) return { status: "clarify", explanation: candidates.length === 0
    ? `The current scene has no ${LABELS[kind]}. Confirm whether you want to add one.`
    : `There are ${candidates.length} matching ${LABELS[kind]} items. Select the one to move from the list below.` };
  return { status: "proposal", mode: "change_furniture", kind, targetCallId: target.call_id, x, y,
    explanation: `Selected ${String(target.arguments.id)} as the ${LABELS[kind]} to move. Only the saved furniture list was checked; the photo and external data were not interpreted. ${x === null && y === null ? "Change X or Y, then" : "Check the position, then"} review the preview. Nothing has been saved.`,
  };
}
