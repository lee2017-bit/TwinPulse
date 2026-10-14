// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
import {useEffect,useRef,useState} from 'react';
import type {TwinPulseApi} from './api';

type ImageOwner={api:TwinPulseApi;context:string;url:string};
const sameOwner=(left:ImageOwner,right:ImageOwner)=>left.api===right.api&&left.context===right.context&&left.url===right.url;

export function AuthenticatedConversationImage({api,url,alt}:{api:TwinPulseApi;url:string;alt:string}){
  const context=api.context??'';
  const owner=useRef<ImageOwner>({api,context,url});owner.current={api,context,url};
  const [decoded,setDecoded]=useState<(ImageOwner&{objectUrl:string;width:number;height:number})|null>(null);
  const [failure,setFailure]=useState<ImageOwner|null>(null);
  const image=decoded&&sameOwner(decoded,owner.current)?decoded:null;
  const failed=!!failure&&sameOwner(failure,owner.current);
  useEffect(()=>{
    const expected={api,context,url};let closed=false,objectUrl:string|null=null,released=false;
    let decoder:HTMLImageElement|null=null,timer:ReturnType<typeof setTimeout>|undefined;
    const current=()=>!closed&&sameOwner(expected,owner.current)&&(api.context??'')===context;
    const release=()=>{if(objectUrl&&!released){released=true;URL.revokeObjectURL(objectUrl);}};
    setFailure(null);
    const load=async()=>{
      try{
        const blob=await api.conversationImage(url);
        if(!current())return;
        if(blob.type!=='image/png'||blob.size===0)throw new Error('Photo response is not a PNG image');
        objectUrl=URL.createObjectURL(blob);decoder=new Image();decoder.src=objectUrl;
        await Promise.race([decoder.decode(),new Promise<never>((_,reject)=>{
          timer=setTimeout(()=>reject(new Error('Photo decode timed out')),2000);
        })]);
        if(!current())return;
        if(decoder.naturalWidth<=0||decoder.naturalHeight<=0)throw new Error('Photo has no decoded pixels');
        setDecoded({...expected,objectUrl,width:decoder.naturalWidth,height:decoder.naturalHeight});
      }catch{
        if(current())setFailure(expected);
        release();
      }finally{
        if(timer!==undefined)clearTimeout(timer);
        if(decoder)decoder.src='';
        if(!current())release();
      }
    };
    void load();
    return()=>{closed=true;if(timer!==undefined)clearTimeout(timer);if(decoder)decoder.src='';release();};
  },[api,context,url]);
  return <span className="authenticated-conversation-image" style={{display:'block'}} data-image-state={failed?'error':image?'ready':'loading'}>
    <img src={image?.objectUrl} alt={alt} hidden={!image||failed} data-decoded-width={image?.width} data-decoded-height={image?.height}/>
    {(!image||failed)&&<small role={failed?'alert':'status'} aria-label={`Photo status: ${alt}`}>
      {failed?'Photo unavailable. Reopen this conversation to try again.':'Loading photo…'}</small>}
  </span>;
}
