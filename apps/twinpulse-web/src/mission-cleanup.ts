// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import type {CurrentGoalState} from './conversation-types';

// Bounded machine diagnoses only; never display arbitrary remote exception text.
export function nativeCleanupLines(job:CurrentGoalState['job']|undefined):string[]{
  const rows=job?.native_cleanup_errors;
  if(!Array.isArray(rows)||rows.length>8)return [];
  const stages=new Set(['navigation_halt','mission_halt','mission_close','mission_final_record','goal_watch_join']);
  return rows.filter(row=>row&&stages.has(row.stage)&&/^[A-Z0-9_]{1,120}$/.test(row.code)
    &&/^[A-Za-z][A-Za-z0-9_]{0,79}$/.test(row.error_type))
    .map(row=>`Native cleanup · ${row.stage}: ${row.code} (${row.error_type})`);
}
