// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {fireEvent,render,screen} from '@testing-library/react';
import {describe,expect,it,vi} from 'vitest';
import {DriveJoystick,joystickDirection} from './DriveJoystick';

describe('fixed-intent joystick',()=>{
  it('uses a neutral zone and cardinal commands, not arbitrary velocity',()=>{
    expect(joystickDirection(0,.1)).toBeNull();expect(joystickDirection(NaN,0)).toBeNull();
    expect(joystickDirection(.2,-.8)).toBe('forward');expect(joystickDirection(0,.8)).toBe('backward');
    expect(joystickDirection(-.8,.2)).toBe('left');expect(joystickDirection(.8,.1)).toBe('right');
  });
  it('captures a gesture, releases/cancels it and refuses locked interaction',()=>{
    const onDirection=vi.fn(),onRelease=vi.fn();
    const view=render(<DriveJoystick disabled={false} onDirection={onDirection} onRelease={onRelease}/>);
    const button=screen.getByRole('button',{name:'Drive joystick'});
    vi.spyOn(button,'getBoundingClientRect').mockReturnValue({left:0,top:0,width:200,height:200,right:200,bottom:200,x:0,y:0,toJSON:()=>{}});
    fireEvent.pointerDown(button,{button:0,pointerId:1,clientX:100,clientY:20});
    expect(onDirection).toHaveBeenCalledWith('forward');
    fireEvent.pointerMove(button,{pointerId:1,clientX:180,clientY:100});
    expect(onDirection).toHaveBeenLastCalledWith('right');
    fireEvent.pointerUp(button,{pointerId:1});expect(onRelease).toHaveBeenCalledTimes(1);
    fireEvent.pointerDown(button,{button:0,pointerId:2,clientX:100,clientY:20});
    fireEvent.pointerCancel(button,{pointerId:2});expect(onRelease).toHaveBeenCalledTimes(2);
    view.rerender(<DriveJoystick disabled onDirection={onDirection} onRelease={onRelease}/>);
    const count=onDirection.mock.calls.length;
    fireEvent.pointerDown(button,{button:0,pointerId:3,clientX:100,clientY:20});
    expect(onDirection.mock.calls.length).toBe(count);
  });
});
