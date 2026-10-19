// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {render,screen,fireEvent} from '@testing-library/react';
import {describe,it,expect} from 'vitest';
import {LidarPointView} from './LidarPointView';
describe('shared sensor-local rendering',()=>{
 it('uses actual returns, omits invalid points and labels historical not world aligned',()=>{
  render(<LidarPointView points={[[1,0],[0,2],[NaN,1]]} source="saved_physical_native_sensor" historical/>);
  expect(screen.getByText(/Recorded scan · not live/)).toBeTruthy();
  const svg=screen.getByRole('img');expect(svg.querySelectorAll('circle').length).toBe(3);
  fireEvent.click(screen.getByRole('checkbox'));expect(svg.querySelectorAll('line').length).toBe(2);
 });
 it('bounds dense real scans without inventing endpoints',()=>{
  render(<LidarPointView points={Array.from({length:8192},(_,i)=>[i/8192,1])} source="physical_native_sensor_unaligned"/>);
  expect(screen.getByRole('img').querySelectorAll('circle').length).toBeLessThanOrEqual(721);
  expect(screen.getByText(/no world alignment or position correction/)).toBeTruthy();
 });
});
