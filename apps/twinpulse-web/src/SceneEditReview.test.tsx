// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SceneEditReview } from "./SceneEditReview";
import type { TwinPulseApi } from "./api";
import type { SiteDraftSummary, WorkflowState } from "./types";

it('previews a reusable adjustable model with explicit XYZ dimensions and choices',async()=>{
  const previewSceneEdit=vi.fn().mockResolvedValue({parent_revision:site.revision,result_revision:'b'.repeat(64),
    affected_before:{},affected_after:{},preserved_object_count:0});
  const modelLibrary=vi.fn().mockResolvedValue({library_version:'environment-model-library-1.0',physical_authority:false,
    models:[{model_id:'home.bed',kind:'bed',family:'home',environments:['home'],tool:'place_furniture',
      dimensions_m:{default:[1.4,2,.9]},variants:['standard','single','double'],finishes:['natural','white','dark']}]});
  render(<SceneEditReview api={{previewSceneEdit,modelLibrary} as unknown as TwinPulseApi} site={site} onApplied={vi.fn()}/>);
  fireEvent.click(screen.getByLabelText('Add furniture'));
  await waitFor(()=>expect((screen.getByLabelText('Adjustable library model') as HTMLInputElement).disabled).toBe(false));
  fireEvent.click(screen.getByLabelText('Adjustable library model'));
  fireEvent.change(screen.getByLabelText('Width X (m)'),{target:{value:'1.6'}});
  fireEvent.change(screen.getByLabelText('Depth Y (m)'),{target:{value:'2.1'}});
  fireEvent.change(screen.getByLabelText('Height (m)'),{target:{value:'1.0'}});
  fireEvent.change(screen.getByLabelText('Model variant'),{target:{value:'double'}});
  fireEvent.change(screen.getByLabelText('Model finish'),{target:{value:'white'}});
  fireEvent.click(screen.getByRole('button',{name:'Preview change'}));
  await waitFor(()=>expect(previewSceneEdit).toHaveBeenCalledWith(expect.any(String),'add',null,
    expect.objectContaining({tool:'place_furniture',arguments:expect.objectContaining({
      catalog_version:'furniture-parametric-1.0',dimensions_m:[1.6,2.1,1.],variant:'double',finish:'white'})})));
  expect(screen.getByText(/home.bed/)).toBeTruthy();
});

const site = {
  revision: "a".repeat(64), original_scene_revision: "a".repeat(64), scene_edit_count: 0,
  objects: [{ id: "room_floor", kind: "floor", shape: "box", position_m: [0, 0, 0], dimensions_m: [5, 5, 0.1] }],
  editable_calls: [{ call_id: "bed_call", tool: "create_box_obstacle", arguments: {
    id: "bed", center_m: [-1, 0], dimensions_m: [1.2, 1.8, 0.5], yaw_deg: 0,
  } }],
} as unknown as SiteDraftSummary;

it('derives a legacy furniture footprint from saved rotated geometry rather than an invented box',()=>{
  const saved={...site,objects:[...site.objects,{id:'old_desk_top',kind:'equipment',shape:'box',
    position_m:[1,1,.75],dimensions_m:[1.2,.6,.06],rotation_rpy_deg:[0,0,90]}],
    editable_calls:[{call_id:'old_desk_call',tool:'place_furniture',arguments:{id:'old_desk',kind:'desk',
      catalog_version:'furniture-blocks-1.0',center_m:[1,1],yaw_deg:90}}]} as SiteDraftSummary;
  render(<SceneEditReview api={{} as TwinPulseApi} site={saved} onApplied={vi.fn()}/>);
  fireEvent.click(screen.getByLabelText('Change furniture'));
  fireEvent.change(screen.getByLabelText('Existing furniture call'),{target:{value:'old_desk_call'}});
  const footprint=screen.getByRole('button',{name:'Drag selected object'});
  expect(parseFloat(footprint.style.width)).toBeCloseTo(12);
  expect(parseFloat(footprint.style.height)).toBeCloseTo(24);
});

it('uses map input for a floor hazard and invalidates saved preview on rotate',async()=>{
  const previewSceneEdit=vi.fn().mockResolvedValue({parent_revision:site.revision,result_revision:'b'.repeat(64),
    operation:{operation_id:'fixture'},preview_digest:'fixture',affected_before:{},affected_after:{},preserved_object_count:1});
  const fixture={...site,editable_calls:[{call_id:'cables',tool:'place_room_item',arguments:{id:'cables',kind:'cable_bundle',label:'Loose cables',
    catalog_version:'room-items-1.0',position_m:[0,0,.05],dimensions_m:[.4,.3,.1],yaw_deg:0,observation_time_utc:null}}]};
  render(<SceneEditReview api={{previewSceneEdit} as unknown as TwinPulseApi} site={fixture} onApplied={vi.fn()}/>);
  fireEvent.click(screen.getByLabelText('Change room item / hazard'));
  fireEvent.change(screen.getByRole('combobox',{name:/^Existing room item call$/}),{target:{value:'cables'}});
  fireEvent.keyDown(screen.getByRole('button',{name:'Drag selected object'}),{key:'ArrowUp'});
  fireEvent.click(screen.getByRole('button',{name:'Preview change'}));
  await waitFor(()=>expect(previewSceneEdit).toHaveBeenCalledWith(expect.any(String),'change','cables',
    expect.objectContaining({arguments:expect.objectContaining({position_m:[0,.05,.05],yaw_deg:0,observation_time_utc:null})})));
  await waitFor(()=>expect((screen.getByRole('button',{name:'Save reviewed change'}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole('button',{name:'Rotate selected object 90°'}));
  expect((screen.getByRole('button',{name:'Save reviewed change'}) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByLabelText('Yaw (°)') as HTMLInputElement).value).toBe('90');
});

it('explains that selected parent and declared attachments share preview/apply/Undo',()=>{
  const attached={...site,editable_calls:[{call_id:'bed',tool:'place_furniture',arguments:{
    id:'bed',kind:'bed',catalog_version:'furniture-blocks-1.0',center_m:[0,0],yaw_deg:0}}],
    placement_contract:{schema_version:'photo-placement-contract-1.0' as const,relations:[{
      id:'blanket',relation:'drape' as const,parent_id:'bed',part:'mattress',anchor:'left',elevation_m:null}]}};
  render(<SceneEditReview api={{} as TwinPulseApi} site={attached} onApplied={vi.fn()}/>);
  fireEvent.click(screen.getByLabelText('Change furniture'));
  fireEvent.change(screen.getByRole('combobox',{name:'Existing furniture call'}),{target:{value:'bed'}});
  expect(screen.getByRole('note').textContent).toContain('blanket');
  expect(screen.getByRole('note').textContent).toContain('same preview');
  expect(screen.getByRole('note').textContent).toContain('too-small support');
});

describe("scene edit review", () => {
  it('previews a floor cable item with explicit geometry without inventing a timestamp or saving',async()=>{
    const previewSceneEdit=vi.fn().mockResolvedValue({operation:{operation_id:'cables'},preview_digest:'digest',
      parent_revision:site.revision,result_revision:'b'.repeat(64),affected_before:{},affected_after:{},preserved_object_count:2});
    const applySceneEdit=vi.fn();
    render(<SceneEditReview api={{previewSceneEdit,applySceneEdit} as unknown as TwinPulseApi} site={site} onApplied={vi.fn()}/>);
    fireEvent.click(screen.getByLabelText('Add room item / hazard'));
    fireEvent.change(screen.getByLabelText('Room item type'),{target:{value:'cable_bundle'}});
    fireEvent.change(screen.getByLabelText('Object ID'),{target:{value:'cables'}});
    fireEvent.change(screen.getByLabelText('Item label'),{target:{value:'Loose floor cables'}});
    fireEvent.change(screen.getByLabelText('Center Z (m)'),{target:{value:'0.05'}});
    fireEvent.change(screen.getByLabelText('Height (m)'),{target:{value:'0.1'}});
    fireEvent.click(screen.getByRole('button',{name:'Preview change'}));
    await waitFor(()=>expect(previewSceneEdit).toHaveBeenCalledWith(expect.stringMatching(/^edit_/),'add',null,
      expect.objectContaining({tool:'place_room_item',arguments:expect.objectContaining({id:'cables',kind:'cable_bundle',
        label:'Loose floor cables',position_m:[0,0,.05],dimensions_m:[.8,.5,.1],observation_time_utc:null})})));
    expect(applySceneEdit).not.toHaveBeenCalled();
    expect(screen.getByText(/synthetic keepout/)).toBeTruthy();
  });
  it("shows loading, previews an offline fake proposal, and never saves before confirmation", async () => {
    let resolveContext!: (value: unknown) => void;
    const sceneEditContext = vi.fn().mockReturnValue(new Promise((resolve) => { resolveContext = resolve; }));
    const previewSceneEditProposal = vi.fn().mockImplementation(async (_id, _text, _selected, _revision, proposal) => ({
      status: "preview", explanation: proposal.explanation, context_sha256: "context_hash",
      preview: { operation: { operation_id: "fake_chair" }, preview_digest: "digest",
        parent_revision: site.revision, result_revision: "b".repeat(64),
        affected_before: {}, affected_after: {}, preserved_object_count: 2 },
    }));
    const applySceneEdit = vi.fn().mockResolvedValue({ phase: "draft_ready" } as WorkflowState);
    render(<SceneEditReview api={{ sceneEditContext, previewSceneEditProposal, applySceneEdit } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "의자 추가 X=0.5 Y=-1.2" } });
    fireEvent.click(screen.getByText("Preview offline simulated proposal"));
    expect(screen.getByRole("status").textContent).toContain("Checking the saved scene edit context");
    expect((screen.getByText("Preview offline simulated proposal") as HTMLButtonElement).disabled).toBe(true);
    resolveContext({ schema_version: "scene-edit-context-1.0", project_id: "demo",
      source_scene_revision: site.revision, current_scene_revision: site.revision,
      request_text: "의자 추가 X=0.5 Y=-1.2", selected_call_id: null, furniture_calls: [],
      scene_objects: [], boundary: "saved scene only", context_sha256: "context_hash" });
    await waitFor(() => expect(previewSceneEditProposal).toHaveBeenCalledWith(
      expect.stringMatching(/^edit_/), "의자 추가 X=0.5 Y=-1.2", null, site.revision,
      expect.objectContaining({ mode: "add_furniture", context_sha256: "context_hash",
        tool_call: expect.objectContaining({ tool: "place_furniture", arguments: expect.objectContaining({
          kind: "chair", center_m: [0.5, -1.2],
        }) }) }),
    ));
    await waitFor(() => expect(screen.queryByText(/Checking the saved scene edit context/)).toBeNull());
    expect(screen.getByText(/existing objects unchanged/)).toBeTruthy();
    expect(applySceneEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Save reviewed change"));
    await waitFor(() => expect(applySceneEdit).toHaveBeenCalledWith({ operation_id: "fake_chair" }, "digest"));
  });

  it("shows a dismissible error popup for a failed edit request", async () => {
    const sceneEditContext = vi.fn().mockRejectedValue(new Error("Scene context is unavailable"));
    render(<SceneEditReview api={{ sceneEditContext } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "의자 추가 X=0.5 Y=0.5" } });
    fireEvent.click(screen.getByText("Preview offline simulated proposal"));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog.textContent).toContain("Scene context is unavailable");
    expect(dialog.textContent).toContain("will not retry automatically");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  it("explains a connection failure instead of showing only Failed to fetch", async () => {
    const sceneEditContext = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    render(<SceneEditReview api={{ sceneEditContext } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "의자 추가 X=0.5 Y=0.5" } });
    fireEvent.click(screen.getByText("Preview offline simulated proposal"));
    expect((await screen.findByRole("alertdialog")).textContent).toContain("Cannot connect to the App server");
  });

  it("shows placement preview failures in the same error popup", async () => {
    const previewSceneEdit = vi.fn().mockRejectedValue(new Error("Furniture overlaps the wall"));
    render(<SceneEditReview api={{ previewSceneEdit } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "소파 추가" } });
    fireEvent.click(screen.getByText("Interpret furniture request"));
    fireEvent.change(screen.getByLabelText("Staged X (m)"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Staged Y (m)"), { target: { value: "0" } });
    fireEvent.click(screen.getByText("Preview all"));
    expect(screen.getByText(/Validating and previewing furniture placement/)).toBeTruthy();
    expect((await screen.findByRole("alertdialog")).textContent).toContain("Furniture overlaps the wall");
  });

  it("previews and applies a typed change only after review; input changes invalidate the preview", async () => {
    const previewSceneEdit = vi.fn().mockResolvedValue({
      operation: { operation_id: "edit_one" }, preview_digest: "digest",
      parent_revision: site.revision, result_revision: "b".repeat(64),
      affected_before: { bed: { position_m: [-1, 0, 0.25], dimensions_m: [1.2, 1.8, 0.5], kind: "equipment" } },
      affected_after: { bed: { position_m: [-0.5, 0, 0.25], dimensions_m: [1.2, 1.8, 0.5], kind: "equipment" } },
      preserved_object_count: 2,
    });
    const applySceneEdit = vi.fn().mockResolvedValue({ phase: "draft_ready" } as WorkflowState);
    const onApplied = vi.fn();
    render(<SceneEditReview api={{ previewSceneEdit, applySceneEdit } as unknown as TwinPulseApi}
      site={site} onApplied={onApplied} />);
    expect(previewSceneEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByLabelText("Change box"));
    fireEvent.change(screen.getByLabelText("Existing box call"), { target: { value: "bed_call" } });
    expect((screen.getByLabelText("Object ID") as HTMLInputElement).value).toBe("bed");
    fireEvent.change(screen.getByLabelText("X (m)"), { target: { value: "-0.5" } });
    fireEvent.click(screen.getByText("Preview change"));
    await screen.findByText(/existing objects unchanged/);
    expect(previewSceneEdit).toHaveBeenCalledWith(expect.stringMatching(/^edit_/), "change", "bed_call",
      { call_id: "bed_call", tool: "create_box_obstacle", arguments: {
        id: "bed", center_m: [-0.5, 0], dimensions_m: [1.2, 1.8, 0.5], yaw_deg: 0,
      } });
    fireEvent.change(screen.getByLabelText("X (m)"), { target: { value: "-0.4" } });
    expect((screen.getByText("Save reviewed change") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Preview change"));
    await waitFor(() => expect((screen.getByText("Save reviewed change") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText("Save reviewed change"));
    await waitFor(() => expect(applySceneEdit).toHaveBeenCalledWith({ operation_id: "edit_one" }, "digest"));
    expect(onApplied).toHaveBeenCalled();
  });

  it("keeps undo disabled until a saved scene edit exists", () => {
    render(<SceneEditReview api={{} as TwinPulseApi} site={site} onApplied={vi.fn()} />);
    expect((screen.getByLabelText("Undo last edit") as HTMLInputElement).disabled).toBe(true);
  });

  it("previews a catalog furniture addition and saves only the reviewed result", async () => {
    const previewSceneEdit = vi.fn().mockResolvedValue({
      operation: { operation_id: "add_chair" }, preview_digest: "chair_digest",
      parent_revision: site.revision, result_revision: "c".repeat(64),
      affected_before: {}, affected_after: { furn_123_chair_seat: {
        position_m: [0.5, 0.4, 0.45], dimensions_m: [0.46, 0.44, 0.06], kind: "equipment",
      } }, preserved_object_count: 2,
    });
    const applySceneEdit = vi.fn().mockResolvedValue({ phase: "draft_ready" } as WorkflowState);
    render(<SceneEditReview api={{ previewSceneEdit, applySceneEdit } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Add furniture"));
    fireEvent.change(screen.getByLabelText("Furniture type"), { target: { value: "chair" } });
    fireEvent.change(screen.getByLabelText("Object ID"), { target: { value: "furn_123_chair" } });
    fireEvent.change(screen.getByLabelText("X (m)"), { target: { value: "0.5" } });
    fireEvent.change(screen.getByLabelText("Y (m)"), { target: { value: "0.4" } });
    fireEvent.click(screen.getByText("Preview change"));
    await screen.findByText(/existing objects unchanged/);
    expect(previewSceneEdit).toHaveBeenCalledWith(expect.stringMatching(/^edit_/), "add", null,
      { call_id: expect.stringMatching(/^edit_/), tool: "place_furniture", arguments: {
        id: "furn_123_chair", kind: "chair", catalog_version: "furniture-blocks-1.0",
        center_m: [0.5, 0.4], yaw_deg: 0,
      } });
    fireEvent.change(screen.getByLabelText("Yaw (°)"), { target: { value: "15" } });
    expect((screen.getByText("Save reviewed change") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Preview change"));
    await waitFor(() => expect((screen.getByText("Save reviewed change") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText("Save reviewed change"));
    await waitFor(() => expect(applySceneEdit).toHaveBeenCalledWith({ operation_id: "add_chair" }, "chair_digest"));
  });

  it("selects an existing furniture call for change and can preview undo", async () => {
    const furnishedSite = { ...site, scene_edit_count: 1, editable_calls: [...(site.editable_calls ?? []),
      { call_id: "desk_call", tool: "place_furniture", arguments: {
        id: "furn_1_desk", kind: "desk", catalog_version: "furniture-blocks-1.0",
        center_m: [0.8, 1.5], yaw_deg: 90,
      } },
    ] } as SiteDraftSummary;
    const previewSceneEdit = vi.fn().mockResolvedValue({
      operation: { operation_id: "change_desk" }, preview_digest: "desk_digest",
      parent_revision: site.revision, result_revision: "d".repeat(64),
      affected_before: {}, affected_after: {}, preserved_object_count: 2,
    });
    render(<SceneEditReview api={{ previewSceneEdit } as unknown as TwinPulseApi}
      site={furnishedSite} onApplied={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Change furniture"));
    fireEvent.change(screen.getByLabelText("Existing furniture call"), { target: { value: "desk_call" } });
    expect(screen.getByLabelText("Current furniture request context").textContent).toContain("furn_1_desk");
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "선택한 가구 이동 X=0.6" } });
    fireEvent.click(screen.getByText("Interpret furniture request"));
    expect(screen.getByText(/Selected furn_1_desk as the desk to move/)).toBeTruthy();
    expect((screen.getByLabelText("X (m)") as HTMLInputElement).value).toBe("0.6");
    expect(previewSceneEdit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "선택한 침대 이동" } });
    fireEvent.click(screen.getByText("Interpret furniture request"));
    expect(screen.getByText(/selected furniture does not match the type named/)).toBeTruthy();
    expect(previewSceneEdit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("X (m)"), { target: { value: "0.8" } });
    expect((screen.getByLabelText("Object ID") as HTMLInputElement).value).toBe("furn_1_desk");
    expect((screen.getByLabelText("Furniture type") as HTMLSelectElement).value).toBe("desk");
    expect((screen.getByText("Preview change") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Furniture type"), { target: { value: "storage" } });
    expect((screen.getByLabelText("Object ID") as HTMLInputElement).value).toBe("furn_1_storage");
    fireEvent.click(screen.getByText("Preview change"));
    await waitFor(() => expect(previewSceneEdit).toHaveBeenCalledWith(expect.stringMatching(/^edit_/),
      "change", "desk_call", { call_id: "desk_call", tool: "place_furniture", arguments: {
        id: "furn_1_storage", kind: "storage", catalog_version: "furniture-blocks-1.0",
        center_m: [0.8, 1.5], yaw_deg: 90,
      } }));
    fireEvent.click(screen.getByLabelText("Undo last edit"));
    fireEvent.click(screen.getByText("Preview change"));
    await waitFor(() => expect(previewSceneEdit).toHaveBeenLastCalledWith(expect.stringMatching(/^edit_/),
      "undo", null, null));
  });

  it("interprets a local furniture request into review fields without saving anything", async () => {
    const previewSceneEdit = vi.fn().mockResolvedValue({
      operation: { operation_id: "request_chair" }, preview_digest: "digest", parent_revision: site.revision,
      result_revision: "c".repeat(64), affected_before: {}, affected_after: {}, preserved_object_count: 2,
    });
    const applySceneEdit = vi.fn();
    render(<SceneEditReview api={{ previewSceneEdit, applySceneEdit } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "의자 추가 X=0.5 Y=-1.2" } });
    fireEvent.click(screen.getByText("Interpret furniture request"));
    expect(screen.getByText(/local furniture-blocks-1.0 preset/)).toBeTruthy();
    expect((screen.getByLabelText("Add furniture") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Furniture type") as HTMLSelectElement).value).toBe("chair");
    expect((screen.getByLabelText("X (m)") as HTMLInputElement).value).toBe("0.5");
    expect((screen.getByLabelText("Y (m)") as HTMLInputElement).value).toBe("-1.2");
    expect(previewSceneEdit).not.toHaveBeenCalled();
    expect(applySceneEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Preview change"));
    await waitFor(() => expect(previewSceneEdit).toHaveBeenCalledWith(expect.any(String), "add", null,
      expect.objectContaining({ tool: "place_furniture", arguments: expect.objectContaining({
        kind: "chair", center_m: [0.5, -1.2],
      }) })));
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "소파 추가" } });
    expect((screen.getByText("Save reviewed change") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Interpret furniture request"));
    expect(screen.getByLabelText("Sofa staged item")).toBeTruthy();
    expect((screen.getByText("Preview all") as HTMLButtonElement).disabled).toBe(true);
  });

  it("stages bed and chair, then previews and saves them as one reviewed operation", async () => {
    const previewSceneEdit = vi.fn().mockResolvedValue({
      operation: { operation_id: "two_furniture" }, preview_digest: "two_digest",
      parent_revision: site.revision, result_revision: "d".repeat(64),
      affected_before: {}, affected_after: { bed_part: {
        position_m: [-1.2, -1.2, 0.2], dimensions_m: [1.4, 2, 0.4], kind: "equipment",
      }, chair_part: {
        position_m: [1.2, -1.2, 0.2], dimensions_m: [.46, .45, .4], kind: "equipment",
      } }, preserved_object_count: 2,
    });
    const applySceneEdit = vi.fn().mockResolvedValue({ phase: "draft_ready" } as WorkflowState);
    render(<SceneEditReview api={{ previewSceneEdit, applySceneEdit } as unknown as TwinPulseApi}
      site={site} onApplied={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Furniture request"), { target: { value: "침대와 의자 추가" } });
    fireEvent.click(screen.getByText("Interpret furniture request"));
    expect(screen.getByLabelText("Bed staged item")).toBeTruthy();
    expect(screen.getByLabelText("Chair staged item")).toBeTruthy();
    expect((screen.getByText("Preview all") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Staged X (m)"), { target: { value: "-1.2" } });
    fireEvent.change(screen.getByLabelText("Staged Y (m)"), { target: { value: "-1.2" } });
    fireEvent.change(screen.getByLabelText("Staged direction"), { target: { value: "180" } });
    fireEvent.click(screen.getByLabelText("Chair staged item"));
    fireEvent.change(screen.getByLabelText("Staged X (m)"), { target: { value: "1.2" } });
    fireEvent.change(screen.getByLabelText("Staged Y (m)"), { target: { value: "-1.2" } });
    fireEvent.change(screen.getByLabelText("Staged direction"), { target: { value: "-90" } });
    expect(applySceneEdit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Preview all"));
    await waitFor(() => expect(previewSceneEdit).toHaveBeenCalledWith(expect.any(String), "add_many", null,
      { calls: [
        expect.objectContaining({ tool: "place_furniture", arguments: expect.objectContaining({ kind: "bed", center_m: [-1.2, -1.2], yaw_deg: 180 }) }),
        expect.objectContaining({ tool: "place_furniture", arguments: expect.objectContaining({ kind: "chair", center_m: [1.2, -1.2], yaw_deg: -90 }) }),
      ] }));
    expect(applySceneEdit).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Staged direction"), { target: { value: "90" } });
    expect((screen.getByText("Save reviewed furniture") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByText("Preview all"));
    await waitFor(() => expect(previewSceneEdit).toHaveBeenCalledTimes(2));
    await waitFor(() => expect((screen.getByText("Save reviewed furniture") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByText("Save reviewed furniture"));
    await waitFor(() => expect(applySceneEdit).toHaveBeenCalledWith({ operation_id: "two_furniture" }, "two_digest"));
  });
});
