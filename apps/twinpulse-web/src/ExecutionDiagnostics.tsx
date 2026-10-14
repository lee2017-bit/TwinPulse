// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { useEffect, useRef, useState } from 'react';
import type { TwinPulseApi } from './api';
import type { RuntimeDiagnostics } from './types';
import './execution-diagnostics.css';

export type DiagnosticMetadata = Record<string, string | number | boolean>;
export type ExecutionSummary = {
  execution_id: string; at: string; stage: string; status: string; duration_s: number | null;
  metadata: DiagnosticMetadata; first_error: DiagnosticMetadata | null;
};
export type DiagnosticHealth = { diagnostics_degraded: boolean; storage_errors: number; dropped_events: number; malformed_events?: number; missing_chunks?: number; duplicate_events?: number; unavailable_executions?: number };
export type ExecutionList = { executions: ExecutionSummary[]; health: DiagnosticHealth; next_cursor?:string|null; has_more?:boolean; scanned_count?:number; page_size?:number; project_id?:string };
export type ExecutionDetail = {
  manifest: { execution_id: string; project_id: string; stage: string; at: string; metadata: DiagnosticMetadata };
  status: string; duration_s: number | null; first_error: DiagnosticMetadata | null;
  spans: { span_id: string; parent_span_id: string | null; stage: string | null; status: string;
    duration_s: number | null; metadata: DiagnosticMetadata }[];
  events: { span_id: string; type: string; at: string; metadata: DiagnosticMetadata }[];
  event_count?: number; events_truncated?: boolean;
  health: DiagnosticHealth; raw_included: false; physical_authority: false;
};
export type ExecutionGraph = {
  schema_version: '1.0'; project_id: string; execution_id: string;
  scope: 'recorded_one_hop_references'; partial: boolean; checked_count: number; reverse_scanned_count: number;
  unavailable_count: number; limits: {nodes:number;edges:number;reverse_records:number;directory_entries:number;total_read_bytes:number;record_read_bytes:number};
  nodes: {execution_id:string;available:boolean;stage:string|null;status:string;at:string|null}[];
  edges: {source:string;target:string;relation:string}[];
  raw_included: false; physical_authority: false;
};
const duration = (value: number | null) => value === null ? 'Not measured' : `${value.toFixed(3)} s`;
const reason = (error: DiagnosticMetadata | null) => error?.error_code ?? error?.error_type ?? 'None';

export function ExecutionDiagnostics({ api, close, initialExecution = null }: { api: TwinPulseApi; close: () => void; initialExecution?: string | null }) {
  const [list, setList] = useState<ExecutionList | null>(null);
  const [runtimeSummary, setRuntimeSummary] = useState<RuntimeDiagnostics|null>(null);
  useEffect(()=>{let active=true;
    if(typeof api.runtimeDiagnostics==='function')void api.runtimeDiagnostics().then(value=>{
      if(active)setRuntimeSummary(value);
    }).catch(()=>{});
    return()=>{active=false;};
  },[api]);
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [draftQuery, setDraftQuery] = useState('');
  const [pages, setPages] = useState<(string|null)[]>([null]);
  const [page, setPage] = useState(0);
  const [trail, setTrail] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [selection, setSelection] = useState<string | null>(initialExecution);
  const [revision, setRevision] = useState(0);
  const [graph, setGraph] = useState<ExecutionGraph|null>(null);
  const [graphBusy, setGraphBusy] = useState(false);
  const [graphError, setGraphError] = useState<string|null>(null);
  const graphRequest = useRef(0);
  const cursor=pages[page];
  function resetPages() { setPages([null]);setPage(0); }
  function openExecution(id:string) {
    if(selection)setTrail(values=>[...values.slice(-31),selection]);
    setSelection(id);setDetail(null);
  }
  useEffect(() => {
    let current = true;
    graphRequest.current += 1; setGraph(null); setGraphError(null); setGraphBusy(false);
    setBusy(true); setError(null);
    // A failed refresh must not leave historical details looking current.
    if (selection) setDetail(null); else setList(null);
    void (selection ? api.executionDiagnostics(selection) : api.executionList({query,status:filter==='all'?'':filter,cursor}))
      .then(value => { if (current) { if ('executions' in value) setList(value); else setDetail(value); } })
      .catch(caught => { if (current) setError(caught instanceof Error ? caught.message : 'Diagnostics unavailable.'); })
      .finally(() => { if (current) setBusy(false); });
    return () => { current = false; graphRequest.current += 1; };
  }, [api, selection, revision, query, filter, cursor]);
  async function readGraph() {
    if (!selection || !detail || busy || graphBusy) return;
    const request = ++graphRequest.current;
    setGraph(null); setGraphError(null); setGraphBusy(true);
    try {
      const value = await api.executionGraph(selection);
      if (request !== graphRequest.current) return;
      if (value.execution_id !== selection || value.project_id !== detail.manifest.project_id ||
          value.schema_version !== '1.0' || value.scope !== 'recorded_one_hop_references' ||
          value.raw_included !== false || value.physical_authority !== false ||
          value.nodes.length > 32 || value.edges.length > 128 ||
          value.nodes.some(node=>! /^[a-f0-9]{32}$/.test(node.execution_id)) ||
          value.edges.some(edge=>![edge.source,edge.target].every(id=>value.nodes.some(node=>node.execution_id===id)))) {
        throw new Error('Linked execution records do not match the selected project.');
      }
      setGraph(value);
    } catch (caught) { if (request === graphRequest.current) setGraphError(caught instanceof Error ? caught.message : 'Linked execution records unavailable.'); }
    finally { if (request === graphRequest.current) setGraphBusy(false); }
  }
  async function exportSelected() {
    if (!selection || busy) return;
    setBusy(true); setError(null);
    try {
      const value = await api.exportExecutionDiagnostics(selection);
      const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = `twinpulse-execution-${selection}.json`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (caught) { setError(caught instanceof Error ? caught.message : 'Export unavailable.'); }
    finally { setBusy(false); }
  }
  const health = detail?.health ?? list?.health;
  const selectedDetail = detail?.manifest.execution_id === selection ? detail : null;
  const profileRows = selectedDetail?.events.filter(event => event.type === 'profile_row') ?? [];
  const invalidProfiles = new Set(profileRows.filter(event => {
    const self = event.metadata.self_s, cumulative = event.metadata.cumulative_s;
    return event.metadata.profile_valid === false || typeof self !== 'number' || typeof cumulative !== 'number' ||
      !Number.isFinite(self) || !Number.isFinite(cumulative) || self < 0 || cumulative < self - .000001;
  }).map(event => event.span_id));
  const profileStatus = (event: ExecutionDetail['events'][number]) => invalidProfiles.has(event.span_id)
    ? 'Invalid measurement · not rankable'
    : selectedDetail?.events_truncated || selectedDetail?.health.diagnostics_degraded
    ? 'Incomplete evidence · not rankable'
    : event.metadata.profile_valid === true && event.metadata.profiler_kind === 'thread_filtered_cprofile' &&
      event.metadata.profile_id === event.span_id ? 'Validated owner-thread profile' : 'Uncalibrated history · not rankable';
  const rows = list?.executions ?? [];
  const related=new Set<string>();
  for(const refs of selectedDetail ? [selectedDetail.manifest.metadata,...selectedDetail.spans.map(span=>span.metadata)] : []) {
    for(const field of ['launch_execution_id','scene_edit_execution_id','command_execution_id',...(refs.evidence_kind==='generation_execution'?['evidence_id']:[])]) {
      const id=refs[field];
      if(typeof id==='string' && /^[a-f0-9]{32}$/.test(id) && id!==selection)related.add(id);
    }
  }
  return <section className="execution-diagnostics" aria-label="Execution diagnostics">
    <header><h2>Execution diagnostics</h2><button onClick={close}>Close diagnostics</button></header>
    <p>App version: {runtimeSummary?.release?.product_version??'not recorded'} · Build: {runtimeSummary?.release?.build_id??'development / not recorded'}{runtimeSummary?.release?.simulation_only?' · SIM-only alpha':''}</p>
    <p>Developer view · read-only. Opening, refreshing and exporting never run a model, engine or robot.</p>
    <p>Command success means its receipt was received, not that a mission or physical stop passed.</p>
    <nav><button disabled={busy} onClick={() => { if(!selection)resetPages();setRevision(value => value + 1); }}>Refresh diagnostics</button>
      {selection && <><button onClick={() => { setSelection(null); setDetail(null);setTrail([]); }}>All executions</button>
        {trail.length>0 && <button disabled={busy} onClick={()=>{setSelection(trail[trail.length-1]);setDetail(null);setTrail(values=>values.slice(0,-1));}}>Back to previous execution</button>}
        <button disabled={busy} onClick={() => void exportSelected()}>Export redacted diagnostics</button></>}
    </nav>
    {busy && <p role="status">Reading saved execution records…</p>}
    {error && <p role="alert">{error}</p>}
    {health?.diagnostics_degraded && <p role="alert">Diagnostics degraded · {health.storage_errors} storage errors · {health.dropped_events} dropped events · {health.malformed_events ?? 0} malformed events · {health.missing_chunks ?? 0} missing chunks · {health.duplicate_events ?? 0} duplicate events ignored · {health.unavailable_executions ?? 0} unavailable executions. Missing records are not proof of success.</p>}
    {!selection && <><form className="diagnostic-search" onSubmit={event=>{event.preventDefault();if(busy)return;setQuery(draftQuery.trim());resetPages();setRevision(value=>value+1);}}>
      <label>Search saved metadata<input aria-label="Search saved metadata" maxLength={160} value={draftQuery} placeholder="Execution, request, mission ID or stage" onChange={event=>setDraftQuery(event.target.value)}/></label>
      <button disabled={busy} type="submit">Search executions</button>
      <button disabled={busy} type="button" onClick={()=>{setDraftQuery('');setQuery('');setFilter('all');resetPages();setRevision(value=>value+1);}}>Clear filters</button>
      <label>Status <select disabled={busy} value={filter} onChange={event => {setFilter(event.target.value);resetPages();}}>
      {['all', 'running', 'succeeded', 'failed', 'cancelled', 'skipped', 'unknown'].map(status => <option key={status}>{status}</option>)}
    </select></label></form>
      <p>Saved observations · newest manifest writes first. Refresh returns to the first page and includes new executions. Running results may change. Search reads safe metadata, not private raw responses.</p>
      <table aria-label="Saved executions"><thead><tr><th>Execution / stage</th><th>Status</th><th>Elapsed</th><th>First error</th></tr></thead>
        <tbody>{rows.map(item => <tr key={item.execution_id}><td data-label="Execution / stage"><button onClick={() => openExecution(item.execution_id)}>{item.execution_id}</button>
          <small>{item.stage} · {item.metadata.mode ?? 'Mode not recorded'} · {item.at}</small></td>
          <td data-label="Status">{item.status}</td><td data-label="Elapsed">{duration(item.duration_s)}</td><td data-label="First error">{reason(item.first_error)}</td></tr>)}</tbody></table>
      {!busy && !error && rows.length === 0 && <p>{list?.has_more ? 'No matches in this scanned page. More saved records remain; choose Older executions.' : 'No saved executions match this page.'}</p>}
      <nav aria-label="Execution pages"><button disabled={busy || page===0} onClick={()=>setPage(value=>value-1)}>Newer executions</button>
        <span>Page {page+1}{list?.scanned_count!==undefined?` · ${list.scanned_count} records checked`:''}</span>
        <button disabled={busy || !list?.next_cursor} onClick={()=>{const next=list?.next_cursor;if(!next)return;setPages(values=>[...values.slice(0,page+1),next]);setPage(value=>value+1);}}>Older executions</button>
      </nav>
    </>}
    {selectedDetail && <><h3>{selectedDetail.manifest.stage} · {selectedDetail.status}</h3>
      {selectedDetail.manifest.stage==='engine_runtime_observation' && <p>This records an engine fault observation, not the full mission duration. Command receipt success is separate. A cleanup failure is not a confirmed stop.</p>}
      {selectedDetail.manifest.stage==='engine_view_observation' && <p>Scene apply succeeded, but its first current frame was not confirmed. This measures backend waiting only; it does not identify a GPU, capture, or network cause. Unknown is not a confirmed rendering failure. No Build or Run is retried automatically.</p>}
      {selectedDetail.manifest.stage==='browser_view_observation' && <p>This is a browser-reported image reception or display failure, not an engine apply failure or a robot safety verdict. Related command receipts remain unchanged. Recovery clears the current display warning, never this saved failure. No Build or Run is retried automatically.</p>}
      {selectedDetail.manifest.stage==='observed_mission' && <p>Phase durations are PC-observed windows, not robot CPU time or one-way network latency. Native survey substeps may be unavailable. A saved correction is separate from its validated robot ACK; an unknown ACK is not success. These records do not authorize motion.</p>}
      <p>Execution: <code>{selectedDetail.manifest.execution_id}</code> · Project: {selectedDetail.manifest.project_id}</p>
      <p>{selectedDetail.manifest.stage==='engine_view_observation'?'Record creation':'Elapsed'}: {duration(selectedDetail.duration_s)} · First error: {reason(selectedDetail.first_error)}</p>
      {related.size>0 && <nav aria-label="Related executions"><span>Related executions</span>{[...related].slice(0,32).map(id=><button disabled={busy} key={id} onClick={()=>openExecution(id)}>{id}</button>)}</nav>}
      <button disabled={busy || graphBusy} onClick={()=>void readGraph()}>Show linked execution graph</button>
      {graphBusy && <p role="status">Reading bounded linked execution records…</p>}
      {graphError && <p role="alert">{graphError}</p>}
      {graph && graph.execution_id===selection && <section className="diagnostic-graph" aria-label="Linked execution graph">
        <h3>Linked execution graph</h3>
        <p>Recorded references only · not a causal verdict. Incoming records reference this execution; outgoing records are referenced by it.</p>
        <p>Reverse lookup: {graph.reverse_scanned_count} of at most {graph.limits.reverse_records} recent records checked. {graph.checked_count} records read. Older links may be outside this snapshot.</p>
        {graph.partial && <p role="alert">Partial graph · missing, damaged, oversized or out-of-range records remain unknown. No missing link proves success.</p>}
        <ul>{graph.edges.map(edge=>{
          const incoming=edge.target===selection;
          const id=incoming?edge.source:edge.target;
          const node=graph.nodes.find(item=>item.execution_id===id)!;
          return <li key={`${edge.source}:${edge.target}:${edge.relation}`}>
            <strong>{incoming?'Incoming':'Outgoing'} · {edge.relation.replaceAll('_',' ')}</strong>
            <button disabled={busy || !node.available} onClick={()=>openExecution(id)}>{id}</button>
            <small>{node.available?`${node.stage} · ${node.status}`:'Unavailable in this project · unknown'}</small>
          </li>;
        })}</ul>
        {graph.edges.length===0 && <p>No linked execution found within this bounded snapshot.</p>}
      </section>}
      {selectedDetail.events_truncated && <p role="alert">Timeline limited to the most recent saved events ({selectedDetail.event_count ?? 'unknown'} total). Earlier stages may be absent; this view and export are not a complete execution history.</p>}
      <h3>Stage timeline</h3><ol>{selectedDetail.spans.map(span => <li key={span.span_id}>
        <strong>{span.stage ?? 'Related evidence'}</strong> · {span.status} · {span.metadata.measurement_source === 'engine_local_elapsed'
          ? `${duration(Number(span.metadata.elapsed_s))} · reported engine-local elapsed`
          : span.metadata.measurement_source === 'backend_local_elapsed' && typeof span.metadata.elapsed_s==='number'
          ? `${duration(span.metadata.elapsed_s)} · measured backend-local waiting`
          : duration(span.duration_s)}
        <small>Span {span.span_id}{span.parent_span_id ? ` · parent ${span.parent_span_id}` : ''}</small>
        <dl>{Object.entries(span.metadata).filter(([key]) => key !== 'stage').map(([key, value]) =>
          <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{String(value)}</dd></div>)}</dl>
      </li>)}</ol>
      {profileRows.length > 0 && <><h3>Function profile</h3>
        <p>Instrumented function time, not unprofiled benchmark speed. Thread CPU excludes waiting; wall includes it. Cumulative rows overlap and must not be added together. Short CPU calls may round to zero.</p>
        {profileRows.some(event => profileStatus(event) !== 'Validated owner-thread profile') &&
          <p role="alert">Unrankable measurements retained for diagnosis. Historical, invalid or incomplete rows are not calibrated bottleneck evidence.</p>}
        <table aria-label="Function profile measurements"><thead><tr><th>Function</th><th>Timer</th><th>Calls</th><th>Self</th><th>Cumulative</th><th>Measurement status</th></tr></thead><tbody>
          {profileRows.map((event, index) => <tr key={index}>
            <td>{event.metadata.source_file}:{event.metadata.source_line ?? '?'}:{event.metadata.function}</td><td>{event.metadata.timer_basis}</td><td>{event.metadata.calls}</td>
            <td>{duration(typeof event.metadata.self_s === 'number' ? event.metadata.self_s : null)}</td>
            <td>{duration(typeof event.metadata.cumulative_s === 'number' ? event.metadata.cumulative_s : null)}</td>
            <td>{profileStatus(event)}</td></tr>)}
        </tbody></table></>}
      <p>Private raw responses and photographs are excluded from export. Unknown is not success.</p>
    </>}
  </section>;
}
