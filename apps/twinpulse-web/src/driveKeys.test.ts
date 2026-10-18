// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { describe, expect, it } from 'vitest';
import { driveDirection, driveKeyBlocked } from './driveKeys';
describe('shared drive key mapping', () => {
  it('uses physical code for Korean input and Caps Lock', () => {
    expect(driveDirection({ code: 'KeyW', key: 'ㅈ' })).toBe('forward');
    expect(driveDirection({ code: 'KeyA', key: 'ㅁ' })).toBe('left');
    expect(driveDirection({ code: 'KeyS', key: 'S' })).toBe('backward');
    expect(driveDirection({ code: 'KeyD', key: 'Process' })).toBe('right');
  });
  it('does not map a different physical key by its text', () => {
    expect(driveDirection({ code: 'KeyQ', key: 'w' })).toBeUndefined();
    expect(driveDirection({ code: '', key: 'W' })).toBe('forward');
  });
  it('protects text editors and browser shortcuts', () => {
    const base = { target: document.body, altKey: false, ctrlKey: false, metaKey: false };
    expect(driveKeyBlocked(base)).toBe(false);
    for (const name of ['altKey', 'ctrlKey', 'metaKey']) expect(driveKeyBlocked({ ...base, [name]: true })).toBe(true);
    const editor = document.createElement('div'); editor.setAttribute('contenteditable', 'true');
    expect(driveKeyBlocked({ ...base, target: editor })).toBe(true);
    expect(driveKeyBlocked({ ...base, target: document.createElement('input') })).toBe(true);
  });
});
