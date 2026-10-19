// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {render,screen,fireEvent} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import type {TwinPulseApi} from './api';
import type {RobotFleetRobot} from './robot-fleet-types';
import {LidarReviewDialog} from './LidarReviewDialog';
describe('explicit sensor review',()=>{
 it('keeps an independent Stop all and closes with Escape without making device requests',()=>{
  const stop=vi.fn(),close=vi.fn(),api={} as TwinPulseApi;
  render(<LidarReviewDialog api={api} robot={{label:'A',scan:null} as RobotFleetRobot} onClose={close} onStopAll={stop}/>);
  expect(screen.getByRole('dialog',{name:'LiDAR sensor review'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Stop all'}));expect(stop).toHaveBeenCalledOnce();
  fireEvent.keyDown(screen.getByRole('dialog'),{key:'Escape'});expect(close).toHaveBeenCalledOnce();
  expect(screen.getByText(/not world localization/)).toBeTruthy();
 });
});
