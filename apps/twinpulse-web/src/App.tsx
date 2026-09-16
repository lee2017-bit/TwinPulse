import { useEffect, useMemo, useState } from "react";
import type { CommandType } from "./engine-contracts";
import { ApiError, fileToBase64, TwinPulseApi } from "./api";
import type { ProductState, WorkflowState } from "./types";

type Screen = "build" | "review" | "simulate";

// Keep the transport identity stable across React renders. Creating this in a
// default parameter would tear down the polling effect after the first state
// update and leave accepted engine operations looking permanently pending.
const DEFAULT_API = new TwinPulseApi();

const EMPTY_PRODUCT: ProductState = {
  project_id: "default",
  engine_connected: false,
  engine_session_id: null,
  stage_epoch: null,
  lease_owned: false,
  control_lease_id: null,
  snapshot: null,
  operations: [],
  artifacts: [],
};

function messageOf(error: unknown): string {
  if (error instanceof ApiError) return `${error.code}: ${error.message}`;
  return error instanceof Error ? error.message : "알 수 없는 오류가 발생했습니다.";
}

function compact(value: string | null | undefined): string {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

export function App({ api = DEFAULT_API }: { api?: TwinPulseApi }) {
  const [screen, setScreen] = useState<Screen>("build");
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [product, setProduct] = useState<ProductState>(EMPTY_PRODUCT);
  const [prompt, setPrompt] = useState("Create a bright warehouse with a clear center aisle and a compact AGV route.");
  const [inputKind, setInputKind] = useState("auto");
  const [file, setFile] = useState<File | null>(null);
  const [sidecar, setSidecar] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [leaseId, setLeaseId] = useState<string | null>(null);

  const refresh = async () => {
    const [nextWorkflow, nextProduct] = await Promise.all([api.workflow(), api.productState()]);
    setWorkflow(nextWorkflow);
    setProduct(nextProduct);
    if (nextProduct.control_lease_id) setLeaseId(nextProduct.control_lease_id);
  };

  useEffect(() => {
    let active = true;
    const boot = async () => {
      try {
        await api.bootstrap();
        if (active) await refresh();
      } catch (caught) {
        if (active) setError(messageOf(caught));
      }
    };
    void boot();
    const timer = window.setInterval(() => {
      if (active) void refresh().catch((caught) => setError(messageOf(caught)));
    }, 500);
    return () => { active = false; window.clearInterval(timer); };
  }, [api]);

  useEffect(() => {
    if (!leaseId) return;
    const timer = window.setInterval(() => {
      void api.renewLease(leaseId).catch((caught) => {
        setLeaseId(null);
        setError(messageOf(caught));
      });
    }, 1_000);
    return () => window.clearInterval(timer);
  }, [api, leaseId]);

  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const draft = workflow?.draft ?? null;
  const snapshot = product.snapshot;
  const latestOperation = product.operations.at(-1) ?? null;
  const applied = Boolean(draft && snapshot?.applied_revision === draft.revision);
  const permitted = new Set(snapshot?.permitted_commands ?? []);
  const telemetryStale = !product.engine_connected || !snapshot;

  const stageLabel = useMemo(() => {
    if (!product.engine_connected) return "Isaac 연결 안 됨";
    if (snapshot?.safety_state) return `안전 정지 · ${snapshot.safety_state}`;
    return `Isaac ${snapshot?.runtime_state ?? "연결 중"}`;
  }, [product.engine_connected, snapshot]);

  const generate = async () => {
    setBusy("generate");
    setError(null);
    try {
      const encoded = file ? await fileToBase64(file) : null;
      const sidecarEncoded = sidecar ? await fileToBase64(sidecar) : null;
      await api.selectInput({
        name: file?.name ?? null,
        input_kind: inputKind,
        prompt,
        media_type: file?.type || null,
        content_base64: encoded,
        sidecar_name: sidecar?.name ?? null,
        sidecar_content_base64: sidecarEncoded,
      });
      let next = await api.generate();
      setWorkflow(next);
      while (next.phase === "generating") {
        await new Promise((resolve) => window.setTimeout(resolve, 120));
        next = await api.workflow();
        setWorkflow(next);
      }
      if (next.phase === "draft_ready") setScreen("review");
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(null);
    }
  };

  const cancelGeneration = async () => {
    try { setWorkflow(await api.cancelGeneration()); }
    catch (caught) { setError(messageOf(caught)); }
  };

  const acknowledge = async () => {
    if (!draft) return;
    setBusy("acknowledge");
    setError(null);
    try { setWorkflow(await api.acknowledge(draft.revision)); }
    catch (caught) { setError(messageOf(caught)); }
    finally { setBusy(null); }
  };

  const ensureLease = async () => {
    if (leaseId) return leaseId;
    const lease = await api.acquireLease();
    setLeaseId(lease.control_lease_id);
    return lease.control_lease_id;
  };

  const command = async (type: CommandType) => {
    setBusy(type);
    setError(null);
    try {
      await ensureLease();
      if (type === "build_scene") {
        if (!draft) throw new Error("검증된 초안이 없습니다.");
        await api.command(type, draft.revision, draft.artifact_id);
      } else {
        await api.command(type, snapshot?.applied_revision ?? draft?.revision ?? null);
      }
      await refresh();
      if (type === "build_scene") setScreen("simulate");
    } catch (caught) {
      setError(messageOf(caught));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="TwinPulse 홈">
          <span className="brand-mark">TP</span>
          <span><strong>TwinPulse</strong><small>Warehouse control room</small></span>
        </a>
        <div className="status-strip" aria-label="연결 상태">
          <Status tone={workflow ? "ok" : "wait"} label={workflow ? "Backend ready" : "Backend connecting"} />
          <Status tone={product.engine_connected ? "ok" : "bad"} label={stageLabel} />
          <Status tone={workflow?.provider.connected ? "ok" : "warn"} label="Live provider 미사용" />
        </div>
      </header>

      <nav className="step-nav" aria-label="작업 단계">
        <Step active={screen === "build"} done={Boolean(draft)} number="01" label="입력 및 생성" onClick={() => setScreen("build")} />
        <Step active={screen === "review"} done={Boolean(workflow?.build_allowed)} number="02" label="장면 검토" onClick={() => setScreen("review")} />
        <Step active={screen === "simulate"} done={applied} number="03" label="시뮬레이션" onClick={() => setScreen("simulate")} />
      </nav>

      <main id="top">
        <section className="hero">
          <div>
            <p className="eyebrow">LOCAL / AUTHENTICATED / ISAAC 6.0.1</p>
            <h1>창고 아이디어를<br /><span>검증 가능한 3D</span>로.</h1>
          </div>
          <div className="truth-card">
            <span>현재 진실의 원천</span>
            <strong>{applied ? "3D 적용 완료" : draft ? "초안 검증됨 · 아직 미적용" : "입력 대기"}</strong>
            <small>UI 문구가 아니라 backend revision과 Isaac snapshot을 비교합니다.</small>
          </div>
        </section>

        {error && <div className="error-banner" role="alert"><strong>확인 필요</strong><span>{error}</span><button onClick={() => setError(null)}>닫기</button></div>}

        {screen === "build" && (
          <section className="workspace two-column" aria-labelledby="build-title">
            <div className="panel form-panel">
              <p className="panel-index">01 / DESCRIBE</p>
              <h2 id="build-title">환경 입력</h2>
              <p className="muted">이미지가 주 증거이며 텍스트는 배치 조건을 보완합니다.</p>
              <label>입력 종류
                <select value={inputKind} onChange={(event) => setInputKind(event.target.value)}>
                  <option value="auto">자동 판별</option><option value="photo">일반 사진</option><option value="drawing">2D 도면</option>
                </select>
              </label>
              <label>자연어 설명
                <textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={5} maxLength={8000} />
              </label>
              <div className="upload-row">
                <label className="upload-button">이미지 선택<input type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => { const selected = event.target.files?.[0] ?? null; setFile(selected); if (!selected) setSidecar(null); }} /></label>
                {file && <button className="text-button" onClick={() => { setFile(null); setSidecar(null); }}>제거</button>}
              </div>
              <p className="fine">PNG/JPG/WEBP · 최대 10 MiB · 경로는 서버에 전달하지 않습니다.</p>
              <div className="upload-row">
                <label className="upload-button secondary">측정 보조 파일 (선택)<input type="file" accept="application/json,.json" disabled={!file} onChange={(event) => setSidecar(event.target.files?.[0] ?? null)} /></label>
                {sidecar && <button className="text-button" onClick={() => setSidecar(null)}>제거</button>}
              </div>
              <p className="fine">치수 도면의 신뢰된 .measurements.json 파일이 있을 때만 선택합니다. 직접 작성할 필요는 없습니다.</p>
              <div className="action-row">
                <button className="primary" disabled={Boolean(busy) || (!prompt.trim() && !file)} onClick={() => void generate()}>{busy === "generate" ? "생성 중…" : "검증 초안 생성"}</button>
                <button disabled={workflow?.phase !== "generating"} onClick={() => void cancelGeneration()}>취소</button>
              </div>
            </div>
            <div className="panel preview-panel">
              <p className="panel-index">REFERENCE</p>
              {preview ? <img src={preview} alt="선택한 창고 참조" /> : <div className="empty-preview"><span>+</span><strong>참조 이미지 없음</strong><small>텍스트만으로도 로컬 fixture 검증은 가능합니다.</small></div>}
              <dl className="meta-list">
                <div><dt>파일</dt><dd>{file?.name ?? "없음"}</dd></div>
                <div><dt>분류</dt><dd>{inputKind}</dd></div>
                <div><dt>측정 보조</dt><dd>{sidecar?.name ?? "없음"}</dd></div>
                <div><dt>생성 모드</dt><dd>Deterministic fixture</dd></div>
              </dl>
            </div>
          </section>
        )}

        {screen === "review" && (
          <section className="workspace" aria-labelledby="review-title">
            <div className="section-heading"><div><p className="panel-index">02 / REVIEW</p><h2 id="review-title">장면 초안 검토</h2></div><span className="revision">REV {compact(draft?.revision)}</span></div>
            {!draft ? <Empty title="검토할 초안이 없습니다" body="입력 및 생성 단계에서 검증 초안을 먼저 만드세요." /> : <>
              <div className="summary-grid">
                <Metric label="허용 도구" value={`${draft.tool_count}`} /><Metric label="장면 객체" value={`${draft.object_count}`} /><Metric label="로봇" value="2WD + caster" /><Metric label="출처" value="local fixture" />
              </div>
              <div className="panel table-wrap"><table><thead><tr><th>ID</th><th>종류</th><th>위치 (m)</th><th>크기 (m)</th><th>출처</th></tr></thead><tbody>{draft.objects.map((item) => <tr key={item.id}><td><code>{item.id}</code></td><td>{item.kind}</td><td>{item.position_m.map((value) => value.toFixed(2)).join(" / ")}</td><td>{item.dimensions_m.map((value) => value.toFixed(2)).join(" × ")}</td><td><span className="source-tag">{item.provenance}</span></td></tr>)}</tbody></table></div>
              <div className="warning-card"><div><strong>개략 3D 모델</strong><p>사진 기반 축척, 가려진 구조와 정확한 장비 위치는 보장되지 않습니다. 정확한 환경에는 치수 도면 또는 스캔을 사용하세요.</p></div><label className="ack"><input type="checkbox" checked={workflow?.acknowledged_revision === draft.revision} disabled={workflow?.acknowledged_revision === draft.revision || Boolean(busy)} onChange={() => void acknowledge()} /> 이 revision의 개략성을 확인했습니다.</label></div>
              <div className="action-row end"><button onClick={() => setScreen("build")}>입력 수정</button><button className="primary" disabled={!workflow?.build_allowed || !product.engine_connected || Boolean(busy)} onClick={() => void command("build_scene")}>{busy === "build_scene" ? "Isaac 적용 중…" : "Isaac에 3D 적용"}</button></div>
            </>}
          </section>
        )}

        {screen === "simulate" && (
          <section className="workspace" aria-labelledby="simulate-title">
            <div className="section-heading"><div><p className="panel-index">03 / SIMULATE</p><h2 id="simulate-title">시뮬레이션 제어</h2></div><Status tone={applied ? "ok" : "warn"} label={applied ? "Revision matched" : "Geometry not applied"} /></div>
            <div className="sim-grid">
              <div className="panel stage-card"><div className="stage-visual"><div className="aisle" /><div className="rack left" /><div className="rack right" /><div className={`agv ${snapshot?.runtime_state === "running" ? "moving" : ""}`} /></div><div className="stage-caption"><span>별도 Isaac 3D 창</span><strong>{snapshot?.runtime_state ?? "연결 대기"}</strong><small>Stage {compact(product.stage_epoch)}</small></div></div>
              <div className="panel telemetry"><h3>실시간 상태</h3><Metric label="목표까지" value={snapshot?.distance_to_goal_m == null ? "—" : `${snapshot.distance_to_goal_m.toFixed(2)} m`} /><Metric label="횡방향 오차" value={snapshot?.cross_track_error_m == null ? "—" : `${snapshot.cross_track_error_m.toFixed(3)} m`} /><Metric label="시뮬레이션 시간" value={snapshot?.sim_time_s == null ? "—" : `${snapshot.sim_time_s.toFixed(1)} s`} /><p className={telemetryStale ? "stale" : "fresh"}>{telemetryStale ? "Telemetry unavailable / stale" : `Sequence ${snapshot?.sequence}`}</p></div>
            </div>
            {snapshot?.safety_state && <div className="safety-banner" role="alert"><strong>{snapshot.safety_state}</strong><span>{snapshot.safety_reason ?? "안전 정지 상태입니다. Reset이 필요할 수 있습니다."}</span></div>}
            <div className="control-bar">
              <button className="run" disabled={!applied || !permitted.has("run") || Boolean(busy)} onClick={() => void command("run")}>▶ Run</button>
              <button disabled={!permitted.has("pause") || Boolean(busy)} onClick={() => void command("pause")}>Ⅱ Pause</button>
              <button disabled={!applied || !permitted.has("reset") || Boolean(busy)} onClick={() => void command("reset")}>↺ Reset</button>
              <button disabled={!product.engine_connected || Boolean(busy)} onClick={() => void command("focus_scene")}>Focus 3D</button>
            </div>
            <div className="operation-line"><span>최근 명령</span><strong>{latestOperation ? `${latestOperation.command_type} · ${latestOperation.status}` : "없음"}</strong><small>{latestOperation?.receipt?.message ?? "명령 결과는 receipt가 확정한 뒤 표시됩니다."}</small></div>
          </section>
        )}
      </main>

      <footer><span>TwinPulse R5 local prototype</span><span>Live provider request: NOT RUN</span></footer>
    </div>
  );
}

function Status({ tone, label }: { tone: "ok" | "wait" | "warn" | "bad"; label: string }) {
  return <span className={`status ${tone}`}><i />{label}</span>;
}

function Step({ active, done, number, label, onClick }: { active: boolean; done: boolean; number: string; label: string; onClick: () => void }) {
  return <button className={active ? "active" : done ? "done" : ""} onClick={onClick}><span>{done ? "✓" : number}</span>{label}</button>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric"><span>{label}</span><strong>{value}</strong></div>;
}

function Empty({ title, body }: { title: string; body: string }) {
  return <div className="panel empty"><strong>{title}</strong><p>{body}</p></div>;
}
