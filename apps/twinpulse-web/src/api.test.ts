// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TwinPulseApi } from "./api";

const jsonResponse = (status: number, body: object): Response => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
}) as Response;

describe("TwinPulse browser session recovery", () => {
  const contextResponse=(context:string,body:object,status=200)=>({...jsonResponse(status,body),
    headers:new Headers({'X-TwinPulse-Context':context})}) as Response;
  it('applies a server-pinned Library preview by ID and digest without round-tripping its operation',async()=>{
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?
      contextResponse('ctx-library',{csrf_token:'csrf-library',context_id:'ctx-library',project_id:'room',project_switch:null}):
      contextResponse('ctx-library',{operation_id:'placement',state:'PREPARED'},202));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    expect(await api.applyLibraryPlacement('saved-preview','digest')).toMatchObject({operation_id:'placement',state:'PREPARED'});
    expect(request).toHaveBeenCalledWith('/v1/product/scene-edit/apply',expect.objectContaining({method:'POST',
      body:JSON.stringify({schema_version:'scene-edit-apply-2.0',library_placement_id:'saved-preview',preview_digest:'digest'}),
      headers:expect.objectContaining({'X-TwinPulse-Context':'ctx-library','X-TwinPulse-CSRF':'csrf-library'})}));
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/scene-edit/apply')).toHaveLength(1);
  });
  it('does not repeat a Library placement POST after unknown network delivery',async()=>{
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/session')return contextResponse('ctx-library',{csrf_token:'csrf-library',context_id:'ctx-library',project_id:'room',project_switch:null});
      throw new TypeError('Response lost');
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.applyLibraryPlacement('saved-preview','digest')).rejects.toThrow('Response lost');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/scene-edit/apply')).toHaveLength(1);
  });
  it('requests normal runtime shutdown with the existing context/CSRF session and an empty body',async()=>{
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?
      contextResponse('ctx-exit',{csrf_token:'csrf-exit',context_id:'ctx-exit',project_id:'default',project_switch:null}):
      contextResponse('ctx-exit',{status:'requested',new_session_required:true},202));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    expect(await api.shutdownRuntime()).toEqual({status:'requested',new_session_required:true});
    const calls=request.mock.calls.filter(([path])=>path==='/v1/product/runtime/shutdown');expect(calls).toHaveLength(1);
    expect(request).toHaveBeenCalledWith('/v1/product/runtime/shutdown',expect.objectContaining({method:'POST',body:'{}',credentials:'same-origin',
      headers:expect.objectContaining({'Content-Type':'application/json','X-TwinPulse-Context':'ctx-exit','X-TwinPulse-CSRF':'csrf-exit'})}));
  });
  it('does not repeat runtime shutdown after unknown network delivery',async()=>{
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/session')return contextResponse('ctx-exit',{csrf_token:'csrf-exit',context_id:'ctx-exit',project_id:'default',project_switch:null});
      throw new Error('Network delivery unknown');
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.shutdownRuntime()).rejects.toThrow('Network delivery unknown');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/runtime/shutdown')).toHaveLength(1);
  });
  it('recovers one known pre-dispatch CSRF rejection in the same project without duplicating unknown work',async()=>{
    let sessions=0,posts=0;
    const request=vi.fn(async(path:string, _init?:RequestInit)=>{
      if(path==='/v1/product/session'){sessions++;return contextResponse('ctx-a',{csrf_token:sessions===1?'old':'new',context_id:'ctx-a',project_id:'a',project_switch:null});}
      posts++;return posts===1?contextResponse('ctx-a',{error:{code:'csrf_rejected',message:'old tab'}},403):contextResponse('ctx-a',{operation_id:'one'});
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    expect(await api.generate()).toMatchObject({operation_id:'one'});
    const mutations=request.mock.calls.filter(([path])=>path==='/v1/product/generation');
    expect(mutations).toHaveLength(2);expect(sessions).toBe(2);
    expect((mutations[1][1] as RequestInit).body).toEqual((mutations[0][1] as RequestInit).body);
    expect((mutations[1][1] as RequestInit).headers).toMatchObject({'X-TwinPulse-CSRF':'new'});
  });
  it('does not resend a CSRF-rejected write after session recovery selects another project',async()=>{
    let sessions=0;
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/session'){sessions++;const context=sessions===1?'ctx-a':'ctx-b';return contextResponse(context,{csrf_token:'csrf',context_id:context,project_id:sessions===1?'a':'b',project_switch:null});}
      return contextResponse('ctx-a',{error:{code:'csrf_rejected',message:'old'}},403);
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.generate()).rejects.toMatchObject({code:'context_changed'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/generation')).toHaveLength(1);
  });
  it('bounds repeated pre-dispatch CSRF rejection to one recovery attempt',async()=>{
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a',project_id:'a',project_switch:null}):
      contextResponse('ctx-a',{error:{code:'csrf_rejected',message:'invalid'}},403));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.generate()).rejects.toMatchObject({code:'csrf_rejected'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/generation')).toHaveLength(2);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(2);
  });
  it('never treats another permission rejection as safe to resend',async()=>{
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}):
      contextResponse('ctx-a',{error:{code:'operation_denied',message:'denied'}},403));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.generate()).rejects.toMatchObject({code:'operation_denied'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/generation')).toHaveLength(1);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(1);
  });
  it('drains an old-project read before switch POST and holds new polls until the selected context is acknowledged',async()=>{
    let finishOld:(value:Response)=>void=()=>{};
    let finishSwitch!:(value:Response)=>void;
    const request=vi.fn((path:string,init:RequestInit)=>{
      if(path==='/v1/product/session')return Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}));
      if(path==='/v1/product/projects/switch')return new Promise<Response>(resolve=>{finishSwitch=resolve;});
      const context=(init.headers as Record<string,string>)['X-TwinPulse-Context'];
      return context==='ctx-a'?new Promise<Response>(resolve=>{finishOld=resolve;}):Promise.resolve(contextResponse('ctx-b',{project_id:'b',revision:1}));
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const old=api.conversation(),switching=api.switchProject('b'),fresh=api.viewportState(),duplicate=api.viewportState(),runtime=api.runtimeState();
    await Promise.resolve();expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(0);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/viewport')).toHaveLength(0);
    finishOld(contextResponse('ctx-a',{project_id:'a',revision:999}));
    expect(await old).toMatchObject({project_id:'a',revision:999});
    await vi.waitFor(()=>expect(finishSwitch).toBeTypeOf('function'));
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/viewport')).toHaveLength(0);
    finishSwitch(contextResponse('ctx-b',{status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false}));await switching;
    expect(await fresh).toMatchObject({project_id:'b'});expect(await duplicate).toMatchObject({project_id:'b'});expect(await runtime).toMatchObject({project_id:'b'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/viewport')).toHaveLength(1);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/runtime')).toHaveLength(1);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(1);
    expect(api.context).toBe('ctx-b');
  });
  it('releases deferred reads in the unchanged owner after a definite switch rejection without retrying the POST',async()=>{
    let failSwitch!:(value:Response)=>void;
    const request=vi.fn((path:string,_init?:RequestInit)=>path==='/v1/product/session'?
      Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'})):
      path==='/v1/product/projects/switch'?new Promise<Response>(resolve=>{failSwitch=resolve;}):
      Promise.resolve(contextResponse('ctx-a',{project_id:'a'})));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const switching=api.switchProject('b'),rejected=expect(switching).rejects.toMatchObject({code:'project_busy'});
    const read=api.viewportState();await vi.waitFor(()=>expect(failSwitch).toBeTypeOf('function'));
    await expect(api.switchProject('c')).rejects.toMatchObject({code:'project_switch_busy'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/viewport')).toHaveLength(0);
    failSwitch(contextResponse('ctx-a',{error:{code:'project_busy',message:'Active operation'}},409));await rejected;
    expect(await read).toMatchObject({project_id:'a'});expect(api.context).toBe('ctx-a');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(1);
  });
  it('preserves the 3-second read deadline and abort before sending a waiting switch',async()=>{
    vi.useFakeTimers();let oldSignal:AbortSignal|undefined;
    const request=vi.fn((path:string,init?:RequestInit)=>{
      if(path==='/v1/product/session')return Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}));
      if(path==='/v1/product/viewport'){oldSignal=init?.signal as AbortSignal;return new Promise<Response>(()=>{});}
      expect(oldSignal?.aborted).toBe(true);
      return Promise.resolve(contextResponse('ctx-b',{status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false}));
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const read=api.viewportState(),failed=expect(read).rejects.toMatchObject({code:'state_read_timeout'}),switching=api.switchProject('b');
    await vi.advanceTimersByTimeAsync(2999);expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);await failed;expect((await switching).status).toBe('switched');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(1);
  });
  it.each(['acquire','renew'])('drains an in-flight lease %s before switch POST and never queues another old lease in the selected context',async kind=>{
    let finishLease!:(value:Response)=>void;
    const path=kind==='acquire'?'/v1/product/lease':'/v1/product/lease/renew';
    const request=vi.fn((url:string)=>url==='/v1/product/session'?
      Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'})):
      url===path?new Promise<Response>(resolve=>{finishLease=resolve;}):
      Promise.resolve(contextResponse('ctx-b',{status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false})));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const lease=kind==='acquire'?api.acquireLease():api.renewLease('old-lease'),switching=api.switchProject('b');
    await expect(api.acquireLease()).rejects.toMatchObject({code:'lease_context_transition'});
    await expect(api.renewLease('old-lease')).rejects.toMatchObject({code:'lease_context_transition'});
    expect(request.mock.calls.filter(([url])=>url==='/v1/product/projects/switch')).toHaveLength(0);
    finishLease(contextResponse('ctx-a',{control_lease_id:'old-lease',ttl_s:3}));expect(await lease).toMatchObject({control_lease_id:'old-lease'});
    expect((await switching).status).toBe('switched');expect(api.context).toBe('ctx-b');
    expect(request.mock.calls.filter(([url])=>url.startsWith('/v1/product/lease'))).toHaveLength(1);
  });
  it.each(['acquire','renew'])('bounds lease %s unknown delivery to 3 seconds without mutation retry and then releases the switch',async kind=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const request=vi.fn((path:string,init?:RequestInit)=>{
      if(path==='/v1/product/session')return Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}));
      if(path.startsWith('/v1/product/lease')){signal=init?.signal as AbortSignal;return new Promise<Response>(()=>{});}
      expect(signal?.aborted).toBe(true);
      return Promise.resolve(contextResponse('ctx-b',{status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false}));
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const lease=kind==='acquire'?api.acquireLease():api.renewLease('old'),failed=expect(lease).rejects.toMatchObject({code:'delivery_unknown'}),switching=api.switchProject('b');
    await vi.advanceTimersByTimeAsync(2999);expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);await failed;expect((await switching).status).toBe('switched');
    expect(request.mock.calls.filter(([path])=>path.startsWith('/v1/product/lease'))).toHaveLength(1);
  });
  it('preserves a definite lease failure and never repeats even a pre-dispatch CSRF rejection',async()=>{
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?
      contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}):contextResponse('ctx-a',{error:{code:'csrf_rejected',message:'Rejected before dispatch'}},403));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.renewLease('old')).rejects.toMatchObject({code:'csrf_rejected'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/lease/renew')).toHaveLength(1);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(1);
  });
  it('rejects a late mutation without repeating it or invalidating the selected session',async()=>{
    let finish:(value:Response)=>void=()=>{};
    const request=vi.fn((path:string)=>path==='/v1/product/session'?
      Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'})):
      path==='/v1/product/projects/switch'?Promise.resolve(contextResponse('ctx-b',{status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false})):
      new Promise<Response>(resolve=>{finish=resolve;}));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const pending=api.generate();const observed=expect(pending).rejects.toMatchObject({code:'context_changed'});
    await api.switchProject('b');finish(contextResponse('ctx-a',{error:{code:'session_rejected'}},401));await observed;
    expect(api.context).toBe('ctx-b');expect(sessionStorage.getItem('twinpulse.csrf')).toBe('csrf');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/generation')).toHaveLength(1);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(1);
  });
  it('rejects mismatched context headers after one bounded read requery',async()=>{
    const request=vi.fn(async(path:string)=>path==='/v1/product/session'?
      contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}):contextResponse('ctx-old',{project_id:'old'}));
    vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    await expect(api.conversation()).rejects.toMatchObject({code:'context_changed'});
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/conversation')).toHaveLength(2);
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(1);
  });
  it('discards a late old-project JPEG before reading its bytes and requests the selected frame',async()=>{
    let finishOld:(value:Response)=>void=()=>{};
    let sessions=0;
    const old=packetResponse(packetState());old.headers.set('X-TwinPulse-Context','ctx-a');
    const next=packetResponse({...packetState(),frame:{...packetState().frame,stage_epoch:'selected-stage'}});next.headers.set('X-TwinPulse-Context','ctx-b');
    const request=vi.fn((path:string,init:RequestInit)=>{
      if(path==='/v1/product/session'){sessions++;const context=sessions===1?'ctx-a':'ctx-b';return Promise.resolve(contextResponse(context,{csrf_token:'csrf',context_id:context,project_id:sessions===1?'a':'b'}));}
      return (init.headers as Record<string,string>)['X-TwinPulse-Context']==='ctx-a'?
        new Promise<Response>(resolve=>{finishOld=resolve;}):Promise.resolve(next as unknown as Response);
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const pending=api.viewportImageFrame();await api.projectContext();finishOld(old as unknown as Response);
    expect((await pending).state.frame?.stage_epoch).toBe('selected-stage');expect(old.arrayBuffer).not.toHaveBeenCalled();
    expect(next.arrayBuffer).toHaveBeenCalledOnce();expect(request.mock.calls.filter(([path])=>path==='/v1/product/session')).toHaveLength(2);
  });
  it('drains sensor map and in-flight JPEG headers before switch POST without extending image timeout',async()=>{
    vi.useFakeTimers();let finishMap!:(value:Response)=>void,imageSignal:AbortSignal|undefined;
    const request=vi.fn((path:string,init?:RequestInit)=>{
      if(path==='/v1/product/session')return Promise.resolve(contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a'}));
      if(path==='/v1/product/automatic-demo/maps')return new Promise<Response>(resolve=>{finishMap=resolve;});
      if(path==='/v1/product/viewport/current'){imageSignal=init?.signal as AbortSignal;return new Promise<Response>(()=>{});}
      expect(imageSignal?.aborted).toBe(true);
      return Promise.resolve(contextResponse('ctx-b',{status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false}));
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const maps=api.automaticMaps(),image=api.viewportImageFrame(),failed=expect(image).rejects.toMatchObject({code:'viewport_http_error'}),switching=api.switchProject('b');
    finishMap(contextResponse('ctx-a',{maps:[]}));expect(await maps).toEqual({maps:[]});
    await vi.advanceTimersByTimeAsync(1999);expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(0);
    await vi.advanceTimersByTimeAsync(1);await failed;expect((await switching).status).toBe('switched');
    expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(1);
  });
  it('recovers a lost switch acknowledgement through session observation without repeating the switch',async()=>{
    vi.useFakeTimers();let sessions=0;
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/projects/switch')throw new TypeError('Lost acknowledgement');
      sessions++;
      return sessions<3?contextResponse('ctx-a',{csrf_token:'csrf',context_id:'ctx-a',project_id:'a',
        project_switch:sessions===2?{switch_id:'pending',project_id:'b'}:null}):
        contextResponse('ctx-b',{csrf_token:'csrf',context_id:'ctx-b',project_id:'b',project_switch:null});
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const pending=api.switchProject('b');await vi.advanceTimersByTimeAsync(501);
    expect(await pending).toEqual({status:'switched',project_id:'b',context_id:'ctx-b',new_session_required:false});
    expect(api.context).toBe('ctx-b');expect(request.mock.calls.filter(([path])=>path==='/v1/product/projects/switch')).toHaveLength(1);
  });
  it('verifies a backend context-changed conflict through session and only retries a read',async()=>{
    let sessions=0,reads=0;
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/session'){sessions++;return contextResponse(sessions===1?'ctx-a':'ctx-b',
        {csrf_token:'csrf',context_id:sessions===1?'ctx-a':'ctx-b',project_id:sessions===1?'a':'b',project_switch:null});}
      reads++;return reads===1?contextResponse('ctx-b',{error:{code:'project_context_changed'}},409):contextResponse('ctx-b',{project_id:'b'});
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    expect(await api.conversation()).toMatchObject({project_id:'b'});expect(api.context).toBe('ctx-b');expect(sessions).toBe(2);expect(reads).toBe(2);
  });
  const packetState=()=>({state:'live',fps:6,age_ms:10,detail:'Fresh',physical_authority:false,camera_pending:false,camera_result:null,
    frame:{frame_id:8,captured_at_ms:Date.now(),applied_revision:'revision',engine_session_id:'engine',stage_epoch:'stage',
      width:960,height:640,camera_sequence:0,sha256:'a'.repeat(64),url:'/v1/product/viewport/frame/8'}});
  const packetResponse=(state:unknown,status=200)=>({ok:true,status,headers:new Headers({'Content-Type':'image/jpeg','X-TwinPulse-Viewport':JSON.stringify(state)}),
    arrayBuffer:vi.fn(async()=>new Uint8Array([255,216,255,217]).buffer)});
  it('reads the current JPEG with its receipt using one no-store same-origin GET',async()=>{
    const response=packetResponse(packetState());const request=vi.fn(async()=>response);vi.stubGlobal('fetch',request);
    const result=await new TwinPulseApi().viewportImageFrame();
    expect(result.state.frame?.frame_id).toBe(8);expect(result.image?.type).toBe('image/jpeg');
    expect(request).toHaveBeenCalledWith('/v1/product/viewport/current',expect.objectContaining({credentials:'same-origin',cache:'no-store'}));
    expect(request).toHaveBeenCalledTimes(1);expect(response.arrayBuffer).toHaveBeenCalledTimes(1);
  });
  it('reads only the authenticated project preview by SHA without a current-frame claim',async()=>{
    const response=packetResponse(packetState());const request=vi.fn(async()=>response);vi.stubGlobal('fetch',request);
    expect((await new TwinPulseApi().viewportPreviewImage('b'.repeat(64))).type).toBe('image/jpeg');
    expect(request).toHaveBeenCalledWith(`/v1/product/viewport/preview/${'b'.repeat(64)}`,
      expect.objectContaining({credentials:'same-origin',cache:'no-store'}));
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('preserves only the exact authenticated preview-expired conflict as a normal replacement',async()=>{
    const request=vi.fn(async()=>jsonResponse(409,{error:{code:'viewport_preview_expired'}}));vi.stubGlobal('fetch',request);
    await expect(new TwinPulseApi().viewportPreviewImage('b'.repeat(64))).rejects.toMatchObject({code:'viewport_preview_expired'});
    expect(request).toHaveBeenCalledTimes(1);
  });
  it.each([403,409,500])('does not hide another preview HTTP %s error as expiration',async status=>{
    const request=vi.fn(async()=>jsonResponse(status,{error:{code:'different_error'}}));vi.stubGlobal('fetch',request);
    await expect(new TwinPulseApi().viewportPreviewImage('b'.repeat(64))).rejects.toMatchObject({code:'viewport_http_error'});
    expect(request).toHaveBeenCalledTimes(1);
  });
  it.each(['../frame/8','https://remote.invalid/image','BAD'])('rejects invalid preview SHA %s before fetching',async sha=>{
    const request=vi.fn();vi.stubGlobal('fetch',request);
    await expect(new TwinPulseApi().viewportPreviewImage(sha)).rejects.toMatchObject({code:'viewport_image_invalid'});
    expect(request).not.toHaveBeenCalled();
  });
  it.each(['fetch','body'])('bounds an unresponsive preview %s read without overlapping retries',async stage=>{
    vi.useFakeTimers();
    try{
      const response=packetResponse(packetState());if(stage==='body')response.arrayBuffer.mockImplementation(()=>new Promise(()=>{}));
      const request=vi.fn((_path:string,_init:RequestInit)=>stage==='fetch'?new Promise(()=>{}):Promise.resolve(response));vi.stubGlobal('fetch',request);
      const pending=new TwinPulseApi().viewportPreviewImage('b'.repeat(64));
      const outcome=expect(pending).rejects.toMatchObject({code:'viewport_http_error'});
      await vi.advanceTimersByTimeAsync(2001);await outcome;
      expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][1].signal?.aborted).toBe(true);
    }finally{vi.useRealTimers();}
  });
  it('finishes the bodyless no-current-frame stream without treating it as an image',async()=>{
    const response=packetResponse({...packetState(),state:'stale',frame:null},204);response.arrayBuffer.mockResolvedValue(new ArrayBuffer(0));vi.stubGlobal('fetch',vi.fn(async()=>response));
    expect((await new TwinPulseApi().viewportImageFrame()).image).toBeNull();expect(response.arrayBuffer).toHaveBeenCalledTimes(1);
  });
  it('rejects unexpected bytes in a no-current-frame receipt',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>packetResponse({...packetState(),state:'waiting',frame:null},204)));
    await expect(new TwinPulseApi().viewportImageFrame()).rejects.toMatchObject({code:'viewport_image_invalid'});
  });
  it('keeps the original atomic timeout while finishing a bodyless response',async()=>{
    vi.useFakeTimers();
    try{
      const response=packetResponse({...packetState(),state:'waiting',frame:null},204);response.arrayBuffer.mockImplementation(()=>new Promise(()=>{}));
      const request=vi.fn(async(_path:string,_init:RequestInit)=>response);vi.stubGlobal('fetch',request);
      const pending=new TwinPulseApi().viewportImageFrame();const outcome=expect(pending).rejects.toMatchObject({code:'viewport_http_error'});
      await vi.advanceTimersByTimeAsync(2001);await outcome;expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][1].signal?.aborted).toBe(true);
    }finally{vi.useRealTimers();}
  });
  it('rechecks the project after the awaited bodyless stream finishes',async()=>{
    const response=packetResponse({...packetState(),state:'waiting',frame:null},204);response.headers.set('X-TwinPulse-Context','ctx-a');
    let finish!:(value:ArrayBuffer)=>void,sessions=0;
    response.arrayBuffer.mockImplementation(()=>new Promise(resolve=>{finish=resolve;}));
    const request=vi.fn(async(path:string)=>{
      if(path==='/v1/product/session'){
        const context=++sessions===1?'ctx-a':'ctx-b';return contextResponse(context,{context_id:context,csrf_token:'test',project_id:context});
      }
      return response;
    });vi.stubGlobal('fetch',request);const api=new TwinPulseApi();await api.bootstrap();
    const pending=api.viewportImageFrame();const outcome=expect(pending).rejects.toMatchObject({code:'context_changed'});
    await vi.waitFor(()=>expect(finish).toBeTypeOf('function'));await api.projectContext();finish(new ArrayBuffer(0));await outcome;
  });
  it.each(['fetch','body'])('bounds an unresponsive atomic %s read even if abort is ignored',async stage=>{
    vi.useFakeTimers();
    try{
      const response=packetResponse(packetState());if(stage==='body')response.arrayBuffer.mockImplementation(()=>new Promise(()=>{}));
      const request=vi.fn((_path:string,_init:RequestInit)=>stage==='fetch'?new Promise(()=>{}):Promise.resolve(response));vi.stubGlobal('fetch',request);
      const pending=new TwinPulseApi().viewportImageFrame();const outcome=expect(pending).rejects.toMatchObject({code:'viewport_http_error'});
      await vi.advanceTimersByTimeAsync(2001);await outcome;
      expect(request).toHaveBeenCalledTimes(1);expect(request.mock.calls[0][1].signal?.aborted).toBe(true);
    }finally{vi.useRealTimers();}
  });
  it.each([0,180001])('rejects atomic JPEG body size %s',async size=>{
    const response=packetResponse(packetState());response.arrayBuffer.mockResolvedValue(new Uint8Array(size).buffer);
    vi.stubGlobal('fetch',vi.fn(async()=>response));
    await expect(new TwinPulseApi().viewportImageFrame()).rejects.toMatchObject({code:'viewport_image_invalid'});
  });
  it.each(['missing_frame','authority','remote_url','bad_dimensions','bad_camera','bad_sha','invalid_json','oversize_header'])('rejects invalid atomic receipt %s without decoding',async fault=>{
    const state=packetState();
    const modified=fault==='missing_frame'?{...state,frame:null}:fault==='authority'?{...state,physical_authority:true}:
      fault==='remote_url'?{...state,frame:{...state.frame,url:'https://remote.invalid/image'}}:
      fault==='bad_dimensions'?{...state,frame:{...state.frame,width:9000}}:
      fault==='bad_camera'?{...state,camera_result:{state:'failed',request_id:'x',code:{private:'body'}}}:
      fault==='bad_sha'?{...state,frame:{...state.frame,sha256:'bad'}}:state;
    const response=packetResponse(modified);
    if(fault==='invalid_json')response.headers.set('X-TwinPulse-Viewport','not json');
    if(fault==='oversize_header')response.headers.set('X-TwinPulse-Viewport','x'.repeat(8193));
    vi.stubGlobal('fetch',vi.fn(async()=>response));
    await expect(new TwinPulseApi().viewportImageFrame()).rejects.toMatchObject({code:'viewport_image_invalid'});
    expect(response.arrayBuffer).not.toHaveBeenCalled();
  });
  it('reads a selected graph once with same-origin auth and no command body',async()=>{
    const request=vi.fn(async(_path:string,_init:RequestInit)=>jsonResponse(200,{}));vi.stubGlobal('fetch',request);
    await new TwinPulseApi().executionGraph('a'.repeat(32));
    const [path,init]=request.mock.calls[0];
    expect(path).toBe('/v1/product/diagnostics/'+'a'.repeat(32)+'/graph');
    expect(init.method??'GET').toBe('GET');expect(init.credentials).toBe('same-origin');
    expect(init.body).toBeUndefined();expect(request).toHaveBeenCalledTimes(1);
  });
  it.each([409,401,404,500,503])('classifies image HTTP %s without retry or reading an error body',async status=>{
    const read=vi.fn();const request=vi.fn(async()=>({ok:false,status,arrayBuffer:read}));
    vi.stubGlobal('fetch',request);
    await expect(new TwinPulseApi().viewportImage(12)).rejects.toMatchObject({code:status===409?'viewport_frame_expired':'viewport_http_error'});
    expect(read).not.toHaveBeenCalled();expect(request).toHaveBeenCalledTimes(1);
  });
  it('encodes diagnostic search and cursors in an authenticated read-only GET',async()=>{
    const request=vi.fn(async(_path:string,_init:RequestInit)=>jsonResponse(200,{executions:[],health:{},next_cursor:null}));vi.stubGlobal('fetch',request);
    await new TwinPulseApi().executionList({query:'mission:one / stage',status:'failed',cursor:'safe-cursor',limit:1});
    const [path,init]=request.mock.calls[0];
    const url=new URL(path,'http://127.0.0.1');
    expect(url.pathname).toBe('/v1/product/diagnostics');expect(url.searchParams.get('q')).toBe('mission:one / stage');
    expect(url.searchParams.get('status')).toBe('failed');expect(url.searchParams.get('cursor')).toBe('safe-cursor');
    expect(url.searchParams.get('limit')).toBe('1');expect(init.method??'GET').toBe('GET');expect(init.credentials).toBe('same-origin');
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('preserves exact JPEG bytes without downloaded-Blob response retention',async()=>{
    const bytes=new Uint8Array([255,216,0,42,255,217]);const downloadedBlob=vi.fn();
    const read=vi.fn(async()=>bytes.buffer);
    const request=vi.fn(async()=>({ok:true,headers:new Headers({'Content-Type':'image/jpeg'}),arrayBuffer:read,blob:downloadedBlob}));
    vi.stubGlobal('fetch',request);
    const value=await new TwinPulseApi().viewportImage(12);
    const actual=await new Promise<ArrayBuffer>(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result as ArrayBuffer);reader.readAsArrayBuffer(value);});
    expect(Array.from(new Uint8Array(actual))).toEqual(Array.from(bytes));expect(value.type).toBe('image/jpeg');
    expect(downloadedBlob).not.toHaveBeenCalled();expect(read).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0]).toHaveLength(2);expect(request).toHaveBeenCalledTimes(1);
  });
  it('rejects wrong frame content before reading bytes without retry',async()=>{
    const read=vi.fn();const request=vi.fn(async()=>({ok:true,headers:new Headers({'Content-Type':'text/html'}),arrayBuffer:read}));
    vi.stubGlobal('fetch',request);
    await expect(new TwinPulseApi().viewportImage(12)).rejects.toMatchObject({code:'viewport_image_invalid'});
    expect(read).not.toHaveBeenCalled();expect(request).toHaveBeenCalledTimes(1);
  });
  afterEach(() => vi.useRealTimers());
  it.each(['fetch','body'])('bounds optional viewer diagnosis %s without retrying unknown delivery',async phase=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fn=vi.fn((_path,init)=>{signal=init.signal;return phase==='fetch'?new Promise<Response>(()=>{}):Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});});
    vi.stubGlobal('fetch',fn);
    const result=new TwinPulseApi().viewportObservation({frame_id:1,engine_session_id:'engine',stage_epoch:'stage',applied_revision:'revision',error_code:'viewport_http_error'}).catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(3001);
    expect(signal?.aborted).toBe(true);expect(fn).toHaveBeenCalledTimes(1);
    expect(await result).toBe('viewport_observation_unknown');
  });
  it.each(['fetch','body'])('bounds SIM Run %s as unknown delivery without retry',async phase=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fn=vi.fn((_path,init)=>{signal=init.signal;return phase==='fetch'?new Promise<Response>(()=>{}):Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});});
    vi.stubGlobal('fetch',fn);const result=new TwinPulseApi().simulationRun('plan','scene','request').catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(15001);expect(await result).toBe('delivery_unknown');expect(signal?.aborted).toBe(true);
    expect(fn).toHaveBeenCalledTimes(1);expect(JSON.parse(fn.mock.calls[0][1].body)).toEqual({client_request_id:'request',command_type:'run',expected_applied_revision:'scene',simulation_id:'plan'});
  });
  it.each(['fetch','body'])('bounds a photo-link %s timeout without retry',async phase=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fn=vi.fn((_path,init)=>{signal=init.signal;return phase==='fetch'?new Promise<Response>(()=>{}):Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});});
    vi.stubGlobal('fetch',fn);const result=new TwinPulseApi().linkSensorPhoto('room','sensor','context',[]).catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(45001);expect(await result).toBe('photo_link_timeout');expect(signal?.aborted).toBe(true);
    expect(fn).toHaveBeenCalledTimes(1);expect(JSON.parse(fn.mock.calls[0][1].body)).toEqual({revision:'room',sensor_revision:'sensor',context_revision:'context',pairs:[]});
  });
  it.each(['fetch','body'])('bounds a sensor-map %s timeout without retry or robot action',async phase=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fn=vi.fn((_path,init)=>{signal=init.signal;return phase==='fetch'?new Promise<Response>(()=>{}):Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});});
    vi.stubGlobal('fetch',fn);
    const result=new TwinPulseApi().locateSensorMap('reference','map','query',12).catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(45001);expect(await result).toBe('sensor_map_timeout');
    expect(signal?.aborted).toBe(true);expect(fn).toHaveBeenCalledTimes(1);
    expect(fn.mock.calls[0][0]).toContain('/room-localization/sensor-map');
    expect(JSON.parse(fn.mock.calls[0][1].body)).toEqual({job_id:'reference',observation_revision:'map',query_job_id:'query',frame:12});
  });
  it.each(['fetch','body'])('bounds a model comparison %s timeout without retry',async phase=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fn=vi.fn((_path,init)=>{signal=init.signal;return phase==='fetch'?new Promise<Response>(()=>{}):Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});});
    vi.stubGlobal('fetch',fn);
    const result=new TwinPulseApi().compareObservationModel('job','room','observed').catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(45001);expect(await result).toBe('model_comparison_timeout');
    expect(signal?.aborted).toBe(true);expect(fn).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fn.mock.calls[0][1].body)).toEqual({job_id:'job',revision:'room',observation_revision:'observed'});
  });
  it('bounds a pending observation map without retrying or sending robot commands',async()=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fn=vi.fn((_path,init)=>{signal=init.signal;return new Promise<Response>(()=>{});});vi.stubGlobal('fetch',fn);
    const result=new TwinPulseApi().sessionObservationMap('a'.repeat(32)).catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(45001);
    expect(await result).toBe('observation_map_timeout');expect(signal?.aborted).toBe(true);
    expect(fn).toHaveBeenCalledTimes(1);expect(fn.mock.calls[0][0]).toContain('/room-localization/observation-map');
  });
  it.each(["fetch", "body"])("bounds a never-settling state %s and aborts the transport", async (phase) => {
    vi.useFakeTimers();
    let signal: AbortSignal | undefined;
    vi.stubGlobal("fetch", vi.fn((_path, init) => {
      signal = init.signal;
      return phase === "fetch" ? new Promise(() => {}) : Promise.resolve({
        ok: true, status: 200, json: () => new Promise(() => {}),
      });
    }));
    const settled = new TwinPulseApi().productState().then(() => "unexpected-success", error => error.code);
    await vi.advanceTimersByTimeAsync(3001);
    expect(await Promise.race([settled, Promise.resolve("still-pending")])).toBe("state_read_timeout");
    expect(signal?.aborted).toBe(true);
  });

  it('gives only the cold project catalog a six-second bound without retry or mutation',async()=>{
    vi.useFakeTimers();let signal:AbortSignal|undefined;
    const fetchMock=vi.fn((_path,init)=>{signal=init.signal;return new Promise<Response>(()=>{});});
    vi.stubGlobal('fetch',fetchMock);
    const settled=new TwinPulseApi().projects().then(()=>'unexpected-success',e=>e.code);
    await vi.advanceTimersByTimeAsync(3001);
    expect(await Promise.race([settled,Promise.resolve('still-pending')])).toBe('still-pending');
    expect(signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(3000);
    expect(await settled).toBe('state_read_timeout');expect(signal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('/v1/product/projects');
  });

  it.each(['fetch','body'])('gives only operation records a bounded 20s %s read while live fleet keeps 3s',async phase=>{
    vi.useFakeTimers();const signals:Record<string,AbortSignal>={};
    const fetchMock=vi.fn((path:string,init:RequestInit)=>{signals[path]=init.signal as AbortSignal;
      return phase==='fetch'?new Promise<Response>(()=>{}):Promise.resolve({ok:true,status:200,json:()=>new Promise(()=>{})});});
    vi.stubGlobal('fetch',fetchMock);const api=new TwinPulseApi(),id='a'.repeat(32);
    const record=api.robotFleetOperation(id).catch(e=>e.code),same=api.robotFleetOperation(id).catch(e=>e.code),live=api.robotFleet().catch(e=>e.code);
    await vi.advanceTimersByTimeAsync(3001);expect(await live).toBe('state_read_timeout');
    expect(await Promise.race([record,Promise.resolve('pending')])).toBe('pending');
    expect(signals['/v1/product/robot-fleet/operations/'+id].aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(17000);expect(await record).toBe('operation_record_timeout');expect(await same).toBe('operation_record_timeout');
    expect(signals['/v1/product/robot-fleet/operations/'+id].aborted).toBe(true);expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls.every(([,init])=>init.method==='GET')).toBe(true);
  });

  it("coalesces pending state reads and permits a fresh read after timeout", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch",fetchMock);
    const api = new TwinPulseApi();
    const reads = [api.workflow(),api.workflow(),api.workflow()].map(p => p.catch(e => e.code));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3001);
    expect(await Promise.all(reads)).toEqual(Array(3).fill("state_read_timeout"));
    fetchMock.mockResolvedValue(jsonResponse(200,{phase:"empty"}));
    await expect(api.workflow()).resolves.toMatchObject({phase:"empty"});
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  beforeEach(() => {
    history.replaceState(null, "", "/");
  });

  it("consumes the fragment bootstrap once and removes it before awaiting the network", async () => {
    history.replaceState(null, "", "/#bootstrap=one-time-secret");
    const fetchMock = vi.fn(async () => {
      expect(window.location.hash).toBe("");
      return jsonResponse(200, { csrf_token: "csrf-1" });
    });
    vi.stubGlobal("fetch", fetchMock);

    await new TwinPulseApi().bootstrap();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/v1/bootstrap", expect.objectContaining({ method: "POST" }));
    expect(sessionStorage.getItem("twinpulse.csrf")).toBe("csrf-1");
  });

  it("keeps only the non-secret robot-console marker for refresh", async () => {
    history.replaceState(null, "", "/#robot-console=1&bootstrap=one-time-secret");
    const fetchMock = vi.fn(async () => {
      expect(window.location.hash).toBe("#robot-console=1");
      return jsonResponse(200, { csrf_token: "csrf-robot" });
    });
    vi.stubGlobal("fetch", fetchMock);
    await new TwinPulseApi().bootstrap();
    expect(window.location.href).not.toContain("one-time-secret");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("rehydrates a new tab from the HttpOnly cookie without another bootstrap secret", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, {
      role: "product", csrf_token: "csrf-reopened",
      idle_expires_in_s: 1800, absolute_expires_in_s: 28000,
    }));
    vi.stubGlobal("fetch", fetchMock);

    await new TwinPulseApi().bootstrap();

    expect(fetchMock).toHaveBeenCalledWith("/v1/product/session", expect.objectContaining({
      method: "GET", credentials: "same-origin",
    }));
    expect(sessionStorage.getItem("twinpulse.csrf")).toBe("csrf-reopened");
  });

  it("clears stale tab state and reports a finite reopen error", async () => {
    sessionStorage.setItem("twinpulse.csrf", "stale");
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(401, {
      error: { code: "session_rejected", message: "expired" },
    })));

    await expect(new TwinPulseApi().bootstrap()).rejects.toMatchObject({
      code: "session_reopen_required",
    });
    expect(sessionStorage.getItem("twinpulse.csrf")).toBeNull();
  });

  it("never retries a rejected state-changing request", async () => {
    sessionStorage.setItem("twinpulse.csrf", "csrf");
    const fetchMock = vi.fn(async () => jsonResponse(401, {
      error: { code: "session_rejected", message: "expired" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(new TwinPulseApi().generate()).rejects.toMatchObject({
      code: "session_reopen_required",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sessionStorage.getItem("twinpulse.csrf")).toBeNull();
  });
});
