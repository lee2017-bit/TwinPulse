// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Presentation-only compatibility for saved Korean recipe records.
// Do not rewrite persisted strings: they participate in existing revision hashes.
export function roomSummary(value: string): string {
  return value === '사용자 방 사진 기반 근사 Twin — 치수·로봇 방향·실측 정합 미검증'
    ? 'Approximate Twin based on the supplied room photo — dimensions, robot orientation, and measured alignment are unverified'
    : /[가-힣]/.test(value) ? 'Saved room preview · legacy description retained in the source record' : value;
}

export function routeLabel(value: string): string {
  return ({
    'A · 경유점 경로': 'A · waypoint route',
    'B · 목표 직행 경로': 'B · direct-to-goal route',
  } as Record<string, string>)[value] ?? (/[가-힣]/.test(value) ? 'Saved route · legacy label retained in the source record' : value);
}
