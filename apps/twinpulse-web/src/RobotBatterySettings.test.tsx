// SPDX-License-Identifier: Apache-2.0
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,describe,expect,it,vi} from 'vitest';
import {RobotBatterySettings,batteryDraftConfig,batteryPreview,type BatteryDisplayConfig} from './RobotBatterySettings';
afterEach(cleanup);
const voltage:BatteryDisplayConfig={schema_version:'robot-battery-display-1.0',mode:'voltage_only',label:'',source:'',points:[]};
const preset:BatteryDisplayConfig={...voltage,mode:'robotis_opencr',label:'ROBOTIS OpenCR reference',source:'https://example.invalid/source',points:[{voltage_v:10.5,percent:0},{voltage_v:12.3,percent:100}]};
describe('battery display settings (supplementary UI, not hardware)',()=>{
  it('has voltage-only fallback and no auto save; custom input validates and interpolates',async()=>{
    const save=vi.fn().mockResolvedValue(true);
    render(<RobotBatterySettings busy={false} onSave={save} presets={{voltage_only:voltage,robotis_opencr:preset}}/>);
    expect(screen.getByRole('combobox')).toHaveProperty('value','voltage_only');expect(save).not.toHaveBeenCalled();
    fireEvent.change(screen.getByRole('combobox'),{target:{value:'custom'}});
    expect(screen.getByRole('button',{name:'Save battery display'})).toHaveProperty('disabled',true);
    fireEvent.change(screen.getByLabelText('Voltage 1'),{target:{value:'10'}});fireEvent.change(screen.getByLabelText('Voltage 2'),{target:{value:'12'}});
    fireEvent.change(screen.getByLabelText('Preview voltage (not a current measurement)'),{target:{value:'11.34'}});
    expect(screen.getByLabelText('Battery conversion preview').textContent).toContain('67%');
    fireEvent.click(screen.getByRole('button',{name:'Save battery display'}));
    await waitFor(()=>expect(save).toHaveBeenCalledExactlyOnceWith({...voltage,mode:'custom',points:[{voltage_v:10,percent:0},{voltage_v:12,percent:100}]}));
  });
  it('preserves unsaved edits across polls and restores saved setting on cancel',()=>{
    const view=render(<RobotBatterySettings config={preset} busy={false} onSave={vi.fn()} presets={{robotis_opencr:preset}}/>);
    fireEvent.change(screen.getByRole('combobox'),{target:{value:'custom'}});
    fireEvent.change(screen.getByLabelText('Voltage 1'),{target:{value:'10'}});
    view.rerender(<RobotBatterySettings config={{...preset}} busy={false} onSave={vi.fn()} presets={{robotis_opencr:preset}}/>);
    expect(screen.getByLabelText('Voltage 1')).toHaveProperty('value','10');
    fireEvent.click(screen.getByRole('button',{name:'Cancel changes'}));expect(screen.getByRole('combobox')).toHaveProperty('value','robotis_opencr');
  });
  it('adds an intermediate point without displacing the 100 percent endpoint',()=>{
    render(<RobotBatterySettings config={preset} busy={false} onSave={vi.fn()} presets={{robotis_opencr:preset}}/>);
    fireEvent.change(screen.getByRole('combobox'),{target:{value:'custom'}});
    fireEvent.click(screen.getByRole('button',{name:'Add table row'}));
    expect(screen.getByLabelText('Percentage 2')).toHaveProperty('value','50');expect(screen.getByLabelText('Percentage 3')).toHaveProperty('value','100');
    expect(screen.getByRole('button',{name:'Save battery display'})).toHaveProperty('disabled',false);
  });
  it('does not accept duplicate/descending points, missing endpoints or nonfinite preview',()=>{
    for(const points of [[{v:'10',p:'0'},{v:'10',p:'100'}],[{v:'12',p:'0'},{v:'10',p:'100'}],[{v:'10',p:'1'},{v:'12',p:'100'}]])
      expect(batteryDraftConfig({mode:'custom',label:'',source:'',points},{})).toBeNull();
    expect(batteryPreview(11.34,preset)).toBe(46.7);expect(batteryPreview(NaN,preset)).toBeNull();expect(batteryPreview(11,voltage)).toBeNull();
  });
});
