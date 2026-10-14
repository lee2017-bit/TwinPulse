// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
export type ViewportTimings={metadata_ms:number;image_ms:number;decode_ms:number;poll_ms:number;frame_age_ms:number;schedule_lag_ms:number};
export type ViewportFrame={frame_id:number;captured_at_ms:number;applied_revision:string;engine_session_id:string;stage_epoch:string;width:number;height:number;
  camera_sequence:number;sha256:string;url:string};
export type ViewportState={state:'waiting'|'live'|'degraded'|'stale';fps:number;age_ms:number|null;detail:string;physical_authority:false;
  camera_pending:boolean;camera_result:{request_id:string;state:'completed'|'failed';code:string}|null;
  frame:ViewportFrame|null;
  last_frame?:(ViewportFrame & {preview_only:true;physical_authority:false})|null};
