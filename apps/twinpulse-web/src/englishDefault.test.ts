/// <reference types="vite/client" />
// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { describe, expect, it } from 'vitest';
import { roomSummary, routeLabel } from './legacyBedroomText';

describe('English-default presentation', () => {
  it('keeps runtime React screen copy in English', () => {
    const files = import.meta.glob('./*.tsx', { query: '?raw', import: 'default', eager: true });
    for (const [name, source] of Object.entries(files)) {
      if (name.endsWith('.test.tsx')) continue;
      expect(source, `${name} contains non-English UI copy`).not.toMatch(/[가-힣]/);
    }
  });
  it('renders saved legacy room labels in English without changing their source records', () => {
    expect(roomSummary('사용자 방 사진 기반 근사 Twin — 치수·로봇 방향·실측 정합 미검증'))
      .toMatch(/^Approximate Twin/);
    expect(routeLabel('A · 경유점 경로')).toBe('A · waypoint route');
    expect(routeLabel('B · 목표 직행 경로')).toBe('B · direct-to-goal route');
    expect(roomSummary('기존 기록')).not.toMatch(/[가-힣]/);
  });
});
