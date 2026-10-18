// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {describe,it,expect,vi} from 'vitest';
import {ModelLibrary} from './ModelLibrary';
import type {TwinPulseApi} from './api';

describe('local model library',()=>{
  it('shows generated provenance, real compiled preview, and only fills a request',async()=>{
    const model={model_id:'local.abc',title:'Open shelf',kind:'storage',family:'home',environments:['home'],tool:'place_model_recipe',
      origin:'model_generated',status:'geometry_sampled',dimensions_m:{default:[1,.4,1.5]},support_parts:['shelf_0'],
      recipe_sha256:'a'.repeat(64),interpreter_version:'model-recipe-compiler-1.0',generator_model:'Nemotron',generation_request_id:'execution-sample',
      preview_parts:[{id:'shelf_0',center:[0,0,.5],size:[1,.4,.02],material:'white',support_top:true}]};
    const lookup=vi.fn().mockResolvedValue({models:[model],physical_authority:false});const use=vi.fn();
    render(<ModelLibrary api={{modelLibrary:lookup} as unknown as TwinPulseApi} close={vi.fn()} useModel={use}/>);
    fireEvent.click(await screen.findByRole('button',{name:/Open shelf/}));
    expect(screen.getByRole('img',{name:'Open shelf compiled model preview'})).toBeTruthy();
    expect(screen.getByText('Generator: Nemotron')).toBeTruthy();
    expect(screen.getByText(/photo\/physical validation not implied/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'Use this model in chat'}));
    expect(use).toHaveBeenCalledWith(model);expect(lookup).toHaveBeenCalledTimes(1);
  });
  it('filters families and never silently conceals lookup failure',async()=>{
    const lookup=vi.fn().mockRejectedValue(new Error('Digest mismatch'));
    render(<ModelLibrary api={{modelLibrary:lookup} as unknown as TwinPulseApi} close={vi.fn()} useModel={vi.fn()}/>);
    expect((await screen.findByRole('alert')).textContent).toContain('Digest mismatch');
    fireEvent.click(screen.getByRole('button',{name:'Refresh library'}));
    await waitFor(()=>expect(lookup).toHaveBeenCalledTimes(2));
  });
  it('preserves an unsent Library asset prompt through Catalog and other workspace tabs',async()=>{
    const api={modelLibrary:vi.fn(async()=>({models:[]})),libraryWorkspace:vi.fn(async()=>({schema_version:'library-workspace-1.0',project_id:'room',current_scene_revision:null,assets:[],jobs:[],extensions:[]})),libraryWorkspaceAction:vi.fn()};
    render(<ModelLibrary api={api as unknown as TwinPulseApi} close={vi.fn()} useModel={vi.fn()}/>);
    fireEvent.click(screen.getByRole('tab',{name:'Create asset'}));
    fireEvent.change(await screen.findByRole('textbox',{name:'Describe Library asset'}),{target:{value:'My unsent chair request'}});
    fireEvent.click(screen.getByRole('tab',{name:'Catalog'}));fireEvent.click(screen.getByRole('tab',{name:'Connections'}));
    fireEvent.click(screen.getByRole('tab',{name:'Create asset'}));
    expect(screen.getByRole('textbox',{name:'Describe Library asset'})).toHaveProperty('value','My unsent chair request');expect(api.libraryWorkspaceAction).not.toHaveBeenCalled();
  });
});
