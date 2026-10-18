// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Physical key positions work with Korean IME / Caps Lock. No global listener.
const directions: Record<string, string> = { KeyW: 'forward', KeyS: 'backward', KeyA: 'left', KeyD: 'right',
  ArrowUp: 'forward', ArrowDown: 'backward', ArrowLeft: 'left', ArrowRight: 'right' };
export function driveDirection(event: { code?: string; key: string }): string | undefined {
  if (event.code) return directions[event.code];
  return directions[event.key] ?? ({ w: 'forward', s: 'backward', a: 'left', d: 'right' } as Record<string, string>)[event.key.toLowerCase()];
}
export function driveKeyBlocked(event: { target: EventTarget | null; altKey: boolean; ctrlKey: boolean; metaKey: boolean }): boolean {
  return event.altKey || event.ctrlKey || event.metaKey || (event.target instanceof Element
    && !!event.target.closest('input,textarea,select,[contenteditable="true"],[contenteditable=""]'));
}
