// SPDX-FileCopyrightText: 2026 Jaewon Lee
// SPDX-License-Identifier: Apache-2.0
// Source: https://github.com/lee2017-bit/TwinPulse
// Read supplied bytes only. Never fetch clipboard URLs or read the OS clipboard.
export function clipboardImage(data:DataTransfer):{image?:File;message?:string}{
  const normalize=(file:File):File|null=>{
    if(file.type.startsWith('image/'))return file;
    if(file.type)return null;
    const extension=file.name.match(/\.(png|jpe?g|webp)$/i)?.[1].toLowerCase();
    if(!extension)return null;
    return new File([file],file.name,{type:extension.startsWith('jp')?'image/jpeg':`image/${extension}`,lastModified:file.lastModified});
  };
  const files=Array.from(data.files??[]).map(normalize).filter((file):file is File=>!!file);
  if(!files.length)for(const item of Array.from(data.items??[])){
    if(item.kind!=='file')continue;
    const file=item.getAsFile();const image=file&&normalize(file);if(image)files.push(image);
  }
  if(files.length>1)return {message:'Paste one image per message. Your current draft and attachment are kept.'};
  if(files.length)return {image:files[0]};
  const html=data.getData?.('text/html')??'';
  if(html.length>14*1024*1024)return {message:'Clipboard image is too large. Attach one PNG, JPEG, or WebP up to 10 MiB.'};
  // Do not insert or parse HTML into a document: remote IMG URLs must not load.
  const imageTags=Array.from(html.matchAll(/<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi));
  if(!imageTags.length)return {};
  if(imageTags.length>1)return {message:'Paste one image per message. Your current draft and attachment are kept.'};
  const src=imageTags[0][1]??imageTags[0][2]??imageTags[0][3];
  const inline=src.match(/^data:(image\/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=\s]+)$/i);
  if(!inline)return {message:'The clipboard contains an image link, not image bytes. Use Copy image (not Copy image address), or Attach a file. No image link was downloaded.'};
  try{
    const content=atob(inline[2].replace(/\s/g,''));
    if(content.length>10*1024*1024)return {message:'Attach one PNG, JPEG, or WebP image up to 10 MiB. Your draft has been kept.'};
    const bytes=new Uint8Array(content.length);for(let i=0;i<content.length;i++)bytes[i]=content.charCodeAt(i);
    const type=inline[1].toLowerCase();
    return {image:new File([bytes],`clipboard.${type==='image/jpeg'?'jpg':type.split('/')[1]}`,{type})};
  }catch{return {message:'Clipboard image bytes could not be read. Copy the image again or Attach a file. Your draft is kept.'};}
}
