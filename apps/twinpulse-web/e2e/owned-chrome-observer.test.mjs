// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {isOwnedTemporaryProfile} from './owned-chrome-observer.mjs';
const root=path.resolve('observer-test-temp');
test('cleanup accepts only the explicit generated temporary leaf',()=>{
  assert.equal(isOwnedTemporaryProfile(path.join(root,'twinpulse-owned-observer-a1B2c3'),root),true);
  for(const unsafe of [root,path.dirname(root),path.join(root,'Default'),
    path.join(root,'twinpulse-owned-observer-'),path.join(root,'twinpulse-owned-observer-a1B2c3','nested'),
    path.join(path.dirname(root),'twinpulse-owned-observer-a1B2c3'),'twinpulse-owned-observer-a1B2c3'])
    assert.equal(isOwnedTemporaryProfile(unsafe,root),false,unsafe);
});
