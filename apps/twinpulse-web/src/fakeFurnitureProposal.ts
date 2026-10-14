// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type { SceneEditContext, SceneEditProposal } from "./types";
import { interpretFurnitureIntent } from "./furnitureIntent";

/** Deterministic fake response for the edit contract; no model, photo or network lookup. */
export function fakeFurnitureProposal(context: SceneEditContext): SceneEditProposal {
  const intent = interpretFurnitureIntent(context.request_text, context.furniture_calls,
    context.selected_call_id ?? "");
  const clarify = (reason: string): SceneEditProposal => ({
    schema_version: "scene-edit-proposal-1.0", context_sha256: context.context_sha256,
    mode: "clarify", target_call_id: null, tool_call: null,
    explanation: `Offline simulated response: ${reason}`.slice(0, 300),
  });
  if (intent.status === "clarify") return clarify(intent.explanation);
  if (intent.status === "staging") return clarify(
    "This verification path proposes one furniture item with known coordinates. Use the staging tool for multiple items or an unknown position.");
  const explanation = `Offline simulated response: ${intent.explanation}`.slice(0, 300);
  if (intent.mode === "add_furniture") {
    if (intent.x === null || intent.y === null) return clarify("Specify both X and Y coordinates.");
    const id = `furn_${crypto.randomUUID().slice(0, 8)}_${intent.kind}`;
    return { schema_version: "scene-edit-proposal-1.0", context_sha256: context.context_sha256,
      mode: "add_furniture", explanation, target_call_id: null,
      tool_call: { call_id: `edit_${crypto.randomUUID().replaceAll("-", "")}`,
        tool: "place_furniture", arguments: { id, kind: intent.kind,
          catalog_version: "furniture-blocks-1.0", center_m: [intent.x, intent.y], yaw_deg: 0 } } };
  }
  if (!context.selected_call_id || intent.targetCallId !== context.selected_call_id) return clarify(
    "Select the furniture to move from the current saved scene first.");
  const call = context.furniture_calls.find((item) => item.call_id === context.selected_call_id);
  const center = call?.arguments.center_m;
  if (!call || !Array.isArray(center) || center.length !== 2 ||
      typeof center[0] !== "number" || typeof center[1] !== "number" ||
      intent.x === null && intent.y === null) return clarify("Check the selected furniture and the new X or Y coordinate.");
  return { schema_version: "scene-edit-proposal-1.0", context_sha256: context.context_sha256,
    mode: "change_furniture", explanation, target_call_id: call.call_id,
    tool_call: { ...call, arguments: { ...call.arguments,
      center_m: [intent.x ?? center[0], intent.y ?? center[1]] } } };
}
