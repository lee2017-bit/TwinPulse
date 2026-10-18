// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import {StrictMode} from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ChatProjects } from './ChatProjects';
import { ApiError, type TwinPulseApi } from './api';
const catalog={projects:[{project_id:'old_room',active:false,status:'review_required'}]};
function harness(){return {projects:vi.fn().mockResolvedValue(catalog),createProject:vi.fn().mockResolvedValue({catalog}),switchProject:vi.fn(async(project_id:string)=>({status:'switched',project_id,context_id:`ctx-${project_id}`,new_session_required:false}))};}
describe('Chat project navigation',()=>{
  it('starts one home-screen New chat outside the effect commit even under StrictMode',async()=>{
    const api=harness();render(<StrictMode><ChatProjects api={api as unknown as TwinPulseApi} launcherReady operationBusy={false}
      report={()=>{}} advanced={()=>{}} newChatRequest={1}/></StrictMode>);
    await screen.findByText('New chat ready.');expect(api.createProject).toHaveBeenCalledOnce();expect(api.switchProject).toHaveBeenCalledOnce();
  });
  it('waits for authentication before loading the project sidebar',async()=>{
    const api=harness();const report=vi.fn();
    const view=render(<ChatProjects api={api as unknown as TwinPulseApi} apiReady={false} launcherReady={true} operationBusy={false} report={report} advanced={()=>{}}/>);
    expect(api.projects).not.toHaveBeenCalled();expect(screen.getByRole('button',{name:'＋ New chat'})).toHaveProperty('disabled',true);
    view.rerender(<ChatProjects api={api as unknown as TwinPulseApi} apiReady={true} launcherReady={true} operationBusy={false} report={report} advanced={()=>{}}/>);
    await screen.findByRole('button',{name:'Open old_room'});expect(api.projects).toHaveBeenCalledOnce();expect(report).not.toHaveBeenCalled();
  });
  it('opens an existing project in the same tab after the switch acknowledgement',async()=>{
    const api=harness();const changed=vi.fn();const address=location.href;
    render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={true} operationBusy={false} report={()=>{}} advanced={()=>{}} onProjectChanged={changed}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Open old_room'}));
    await waitFor(()=>expect(api.switchProject).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/Opened old_room/)).toBeTruthy();
    expect(changed).toHaveBeenCalledWith({status:'switched',project_id:'old_room',context_id:'ctx-old_room',new_session_required:false});
    expect(location.href).toBe(address);expect(screen.getByRole('button',{name:'＋ New chat'})).toHaveProperty('disabled',false);
  });
  it('shows the reason an active job blocks opening a project',async()=>{
    const api=harness();render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={true} operationBusy={true} report={()=>{}} advanced={()=>{}}/>);
    expect(await screen.findByRole('button',{name:'Open old_room'})).toHaveProperty('disabled',true);
    expect(screen.getByText('Finish the active operation before switching projects.')).toBeTruthy();expect(api.switchProject).not.toHaveBeenCalled();
  });
  it('queries a lost create response and does not repeat or switch the project',async()=>{
    const api=harness();api.createProject.mockRejectedValue(new TypeError('response lost'));
    render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={true} operationBusy={false} report={()=>{}} advanced={()=>{}}/>);
    await screen.findByRole('button',{name:'Open old_room'});
    fireEvent.click(screen.getByText('Manage projects'));
    fireEvent.change(screen.getByRole('textbox',{name:'New project name'}),{target:{value:'old_room'}});fireEvent.click(screen.getByRole('button',{name:'Create project'}));
    expect(await screen.findByText(/is present in the saved catalog/)).toBeTruthy();
    expect(api.createProject).toHaveBeenCalledTimes(1);expect(api.switchProject).not.toHaveBeenCalled();
  });
  it('opens the active conversation without launcher restart or mutation',async()=>{
    const api=harness();api.projects.mockResolvedValue({projects:[{project_id:'old_room',active:true,status:'review_required',display_name:'침실 수정',message_count:4}]} as never);
    const open=vi.fn();render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={false} operationBusy={false} report={()=>{}} advanced={()=>{}} currentProject="old_room" openCurrent={open}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Open old_room'}));
    expect(open).toHaveBeenCalledOnce();expect(api.switchProject).not.toHaveBeenCalled();expect(api.createProject).not.toHaveBeenCalled();
  });
  it('creates a new independent project and switches only after acknowledged creation',async()=>{
    const api=harness();const activity=vi.fn();const changed=vi.fn();render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={true} operationBusy={false} report={()=>{}} advanced={()=>{}} activityChanged={activity} onProjectChanged={changed}/>);
    fireEvent.click(screen.getByRole('button',{name:'＋ New chat'}));
    await waitFor(()=>expect(api.switchProject).toHaveBeenCalledOnce());
    const id=api.createProject.mock.calls[0][0];expect(id).toMatch(/^chat_[a-z0-9]+_[a-f0-9]{8}$/);
    expect(api.switchProject).toHaveBeenCalledWith(id);expect(api.createProject).toHaveBeenCalledOnce();
    await waitFor(()=>expect(activity).toHaveBeenLastCalledWith({busy:false,message:'New chat ready.'}));
    expect(changed).toHaveBeenCalledWith(expect.objectContaining({project_id:id,context_id:`ctx-${id}`}));
  });
  it('never switches or repeats after an unknown new-chat creation response',async()=>{
    const api=harness();api.createProject.mockRejectedValue(new TypeError('response lost'));
    render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={true} operationBusy={false} report={()=>{}} advanced={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'＋ New chat'}));
    expect(await screen.findByText(/New chat outcome is unconfirmed/)).toBeTruthy();
    expect(api.createProject).toHaveBeenCalledOnce();expect(api.switchProject).not.toHaveBeenCalled();
  });
  it('reuses the created chat after a confirmed failed switch',async()=>{
    const api=harness();api.switchProject.mockRejectedValueOnce(new ApiError('project_switch_busy','Wait for the current operation.'));
    render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady={true} operationBusy={false} report={()=>{}} advanced={()=>{}}/>);
    fireEvent.click(screen.getByRole('button',{name:'＋ New chat'}));
    await screen.findByText('Wait for the current operation.');
    fireEvent.click(screen.getByRole('button',{name:'＋ New chat'}));
    await waitFor(()=>expect(api.switchProject).toHaveBeenCalledTimes(2));
    expect(api.createProject).toHaveBeenCalledOnce();
    expect(api.switchProject.mock.calls[0][0]).toBe(api.switchProject.mock.calls[1][0]);
  });
  it('keeps a failed project-list read scoped and clears only that issue after the same read succeeds',async()=>{
    const api=harness(),report=vi.fn();api.projects.mockRejectedValueOnce(new ApiError('state_read_timeout','Local state read exceeded 3 seconds.'));
    render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady operationBusy={false} report={report} advanced={()=>{}}/>);
    expect((await screen.findByRole('alert',{name:'Saved project list read issue'})).textContent).toContain('Local state read exceeded 3 seconds.');
    expect(report).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Retry project list · read only'}));
    await screen.findByRole('button',{name:'Open old_room'});expect(screen.queryByRole('alert',{name:'Saved project list read issue'})).toBeNull();
    expect(api.projects).toHaveBeenCalledTimes(2);expect(api.createProject).not.toHaveBeenCalled();expect(api.switchProject).not.toHaveBeenCalled();
  });
  it('retains the last catalog during a refresh failure and does not clear a separate operation error',async()=>{
    const api=harness(),report=vi.fn();api.switchProject.mockRejectedValueOnce(new ApiError('project_switch_busy','Active scene operation is not complete.'));
    render(<ChatProjects api={api as unknown as TwinPulseApi} launcherReady operationBusy={false} report={report} advanced={()=>{}}/>);
    fireEvent.click(await screen.findByRole('button',{name:'Open old_room'}));await waitFor(()=>expect(report).toHaveBeenCalledWith('Active scene operation is not complete.'));
    api.projects.mockRejectedValueOnce(new ApiError('state_read_timeout','Local state read exceeded 3 seconds.'));
    fireEvent.click(screen.getByRole('button',{name:'Manage projects'}));fireEvent.click(screen.getByRole('button',{name:'Refresh projects'}));
    await screen.findByRole('alert',{name:'Saved project list read issue'});expect(screen.getByRole('button',{name:'Open old_room'})).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Retry project list · read only'}));
    await waitFor(()=>expect(screen.queryByRole('alert',{name:'Saved project list read issue'})).toBeNull());
    expect(report).toHaveBeenCalledExactlyOnceWith('Active scene operation is not complete.');
  });
  it('does not publish a delayed old-context project-list failure after the context changes',async()=>{
    const api=Object.assign(harness(),{context:'old'}),report=vi.fn();let fail!:(error:Error)=>void;
    api.projects.mockImplementationOnce(()=>new Promise((_resolve,reject)=>{fail=reject;}));
    const component=()=> <ChatProjects api={api as unknown as TwinPulseApi} launcherReady operationBusy={false} report={report} advanced={()=>{}}/>;
    const view=render(component());api.context='new';view.rerender(component());await screen.findByRole('button',{name:'Open old_room'});
    await act(async()=>{fail(new Error('Old list timeout'));});expect(screen.queryByRole('alert',{name:'Saved project list read issue'})).toBeNull();expect(report).not.toHaveBeenCalled();
  });
});
