// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {act,render,screen} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import {LidarScanView,scanPoints,type ScanPreview} from './LidarScanView';
export function scanFixture():ScanPreview{return {schema:'lidar-display-1.0',frame_id:'base_scan',source_stamp_ns:1,
  sample_s:20,receipt_s:20,angle_min_rad:0,angle_increment_rad:Math.PI/2,range_min_m:.05,range_max_m:8,
  ranges_m:[1,null,1,1],display_only:true,alignment_verified:false,receipt_age_s:0,source_age_at_emit_s:0,transport_delay_measured:false};}
describe('display-only scan',()=>{
  it('preserves signed angular order without reversing original ranges',()=>{
    const scan={...scanFixture(),angle_increment_rad:-Math.PI/2,ranges_m:[1,1,null,1]};
    const original=[...scan.ranges_m];const points=scanPoints(scan,4);
    expect(points[1].x).toBeGreaterThan(250);expect(points[1].y).toBeCloseTo(250);
    expect(scan.ranges_m).toEqual(original);expect(points).toHaveLength(3);
  });
  it('projects sensor X upwards, skips missing/out-of-range rays and never joins gaps',()=>{
    const scan=scanFixture(),points=scanPoints(scan,4);
    expect(points).toHaveLength(3);expect(points[0].x).toBeCloseTo(250);expect(points[0].y).toBeCloseTo(196.25);
    expect(scanPoints({...scan,ranges_m:[Infinity,NaN,0,9]},4)).toEqual([]);
  });
  it('marks lost/ended data stale without pretending it is a mapped room',()=>{
    vi.useFakeTimers();
    try{const view=render(<LidarScanView scan={scanFixture()} active pending={false}/>);
      expect(screen.getByText('Receiving /scan')).toBeTruthy();
      act(()=>vi.advanceTimersByTime(1800));expect(screen.getByText(/Stale scan/)).toBeTruthy();
      view.rerender(<LidarScanView scan={scanFixture()} active={false} pending={false}/>);
      expect(screen.getByText('Stopped · last scan')).toBeTruthy();
      expect(screen.getByText(/not a mapped room/)).toBeTruthy();
    }finally{vi.useRealTimers();}
  });
});
