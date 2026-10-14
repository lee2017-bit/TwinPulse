// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { describe, expect, it } from "vitest";
import { interpretFurnitureIntent } from "./furnitureIntent";
import type { SiteDraftSummary } from "./types";

const calls: NonNullable<SiteDraftSummary["editable_calls"]> = [
  { call_id: "bed_one", tool: "place_furniture", arguments: { id: "furn_1_bed", kind: "bed", center_m: [-1, 0] } },
  { call_id: "bed_two", tool: "place_furniture", arguments: { id: "furn_2_bed", kind: "bed", center_m: [1, 0] } },
  { call_id: "desk_one", tool: "place_furniture", arguments: { id: "furn_1_desk", kind: "desk", center_m: [1, 1] } },
  { call_id: "legacy_box", tool: "create_box_obstacle", arguments: { id: "sofa", kind: "sofa" } },
];

describe("offline furniture request interpretation", () => {
  it("proposes one catalog addition without inventing placement or photo evidence", () => {
    expect(interpretFurnitureIntent("소파 추가", calls)).toMatchObject({
      status: "staging", kinds: ["sofa"],
    });
    expect(interpretFurnitureIntent("의자 배치 X=0.5 Y=-1.2", calls)).toMatchObject({
      status: "proposal", mode: "add_furniture", kind: "chair", x: 0.5, y: -1.2,
    });
  });

  it("requires explicit target when the kind is ambiguous or 'selected' has no selection", () => {
    expect(interpretFurnitureIntent("침대 이동", calls).status).toBe("clarify");
    expect(interpretFurnitureIntent("선택한 침대 이동", calls).status).toBe("clarify");
    expect(interpretFurnitureIntent("선택한 침대 이동 X=-0.5", calls, "bed_two")).toMatchObject({
      status: "proposal", mode: "change_furniture", kind: "bed", targetCallId: "bed_two", x: -0.5, y: null,
    });
    expect(interpretFurnitureIntent("책상 이동", calls)).toMatchObject({
      status: "proposal", mode: "change_furniture", targetCallId: "desk_one",
    });
    expect(interpretFurnitureIntent("선택한 가구 이동 X=-0.5", calls, "bed_two")).toMatchObject({
      status: "proposal", mode: "change_furniture", kind: "bed", targetCallId: "bed_two", x: -0.5,
    });
    expect(interpretFurnitureIntent("선택한 가구 이동", calls).status).toBe("clarify");
    expect(interpretFurnitureIntent("선택한 침대 이동", calls, "desk_one").status).toBe("clarify");
    expect(interpretFurnitureIntent("선택한 가구 추가", calls, "bed_one").status).toBe("clarify");
    expect(interpretFurnitureIntent("선택한 가구 이동", calls, "legacy_box").status).toBe("clarify");
  });

  it("does not guess absent furniture, mixed requests, unsupported verbs or one-sided add coordinates", () => {
    for (const request of ["소파 이동", "침대와 의자 추가 이동", "의자 삭제", "의자 추가 이동",
      "아파트처럼 꾸며줘", "의자 추가 X=1", "", "x".repeat(201)]) {
      expect(interpretFurnitureIntent(request, calls).status, request).toBe("clarify");
    }
  });

  it("stages both named furniture pieces without guessing their positions", () => {
    expect(interpretFurnitureIntent("침대와 의자 추가", calls)).toMatchObject({
      status: "staging", kinds: ["bed", "chair"],
    });
  });
});
