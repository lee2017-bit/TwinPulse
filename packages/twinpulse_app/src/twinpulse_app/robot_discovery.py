# SPDX-FileCopyrightText: 2026 Jaewon Lee
# SPDX-License-Identifier: Apache-2.0
# Source: https://github.com/lee2017-bit/TwinPulse
"""Explicit network responses, separate from remembered OS device inventory."""
import hashlib
import os
import re
import socket
import struct
import time

SERVICES = ('_twinpulse._tcp.local', '_ssh._tcp.local')


def _name(raw, offset, seen=None):
    seen = set() if seen is None else seen
    if offset in seen or len(seen)>24:
        raise ValueError('DNS_NAME_LOOP')
    seen.add(offset); labels=[]; end=None
    for _ in range(128):
        if offset>=len(raw):raise ValueError('DNS_TRUNCATED')
        size=raw[offset];offset+=1
        if size==0:return '.'.join(labels), end or offset
        if size&0xc0==0xc0:
            if offset>=len(raw):raise ValueError('DNS_TRUNCATED')
            pointer=((size&0x3f)<<8)|raw[offset]
            label,_=_name(raw,pointer,seen)
            labels.append(label);return '.'.join(labels),end or offset+1
        if size>63 or offset+size>len(raw):raise ValueError('DNS_LABEL_INVALID')
        labels.append(raw[offset:offset+size].decode('utf-8',errors='strict'));offset+=size
        if sum(map(len,labels))>253:raise ValueError('DNS_NAME_TOO_LONG')
    raise ValueError('DNS_NAME_TOO_LONG')


def dns_records(raw, *, include_ttl=False):
    if not isinstance(raw,bytes) or not 12<=len(raw)<=9000:raise ValueError('DNS_PACKET_INVALID')
    _ident,flags,questions,answers,authority,additional=struct.unpack('!6H',raw[:12])
    if not flags&0x8000 or questions>32 or answers+authority+additional>256:raise ValueError('DNS_PACKET_LIMIT')
    offset=12; result=[]
    for _ in range(questions):
        _,offset=_name(raw,offset);offset+=4
        if offset>len(raw):raise ValueError('DNS_TRUNCATED')
    for _ in range(answers+authority+additional):
        name,offset=_name(raw,offset)
        if offset+10>len(raw):raise ValueError('DNS_TRUNCATED')
        kind,_class,ttl,size=struct.unpack('!HHIH',raw[offset:offset+10]);offset+=10
        end=offset+size
        if end>len(raw):raise ValueError('DNS_TRUNCATED')
        if ttl or include_ttl:
            value=None
            if kind==12:
                target,consumed=_name(raw,offset)
                if consumed>end:raise ValueError('DNS_RDATA_INVALID')
                value=(name,'PTR',target)
            elif kind==33 and size>=7:
                _priority,_weight,port=struct.unpack('!HHH',raw[offset:offset+6])
                target,consumed=_name(raw,offset+6)
                if consumed>end:raise ValueError('DNS_RDATA_INVALID')
                if port:value=(name,'SRV',(target,port))
            elif kind==1 and size==4:value=(name,'A',socket.inet_ntop(socket.AF_INET,raw[offset:end]))
            if value:result.append((*value,ttl) if include_ttl else value)
        offset=end
    return result


def advertised_candidates(records):
    services={value.casefold() for name,kind,value in records if kind=='PTR' and name.casefold() in SERVICES}
    addresses={name.casefold():value for name,kind,value in records if kind=='A'}
    result=[]
    for name,kind,value in records:
        if kind!='SRV' or name.casefold() not in services:continue
        host,port=value;host=host.casefold()
        if not host.endswith('.local') or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',part) for part in host.split('.')):continue
        address=addresses.get(host,host)
        identifier=hashlib.sha256((name.casefold()+'|'+address+'|'+str(port)).encode()).hexdigest()
        label=name.split('._',1)[0][:80]
        if any(ord(c)<32 for c in label):continue
        result.append({'candidate_id':identifier,'transport':'network','address':address,'label':label or host,
                       'hostname':host,'service_instance':name,
                       'identity_verified':False,'adapter_id':None,
                       'endpoint':{'host':address,'user':'twinpulse','port':port,'ros_domain_id':86}})
    return list({row['candidate_id']:row for row in result}.values())[:64]


def advertised_network(*, socket_factory=socket.socket, clock=time.monotonic, timeout_s=3.0):
    records={};observed={};state='completed'
    try:
        with socket_factory(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP) as client:
            client.settimeout(.25);client.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,1)
            client.bind(('',0))
            query=struct.pack('!6H',0,0,len(SERVICES),0,0,0)
            for service in SERVICES:
                query+=b''.join(bytes([len(label)])+label.encode('ascii') for label in service.split('.'))+b'\0'+struct.pack('!HH',12,0x8001)
            client.sendto(query,('224.0.0.251',5353))
            deadline=clock()+min(max(timeout_s,.1),5.)
            for _ in range(128):
                if clock()>=deadline:break
                try:raw,_peer=client.recvfrom(9001)
                except socket.timeout:continue
                try:
                    now=clock()
                    for name,kind,value,ttl in dns_records(raw,include_ttl=True):
                        normalized=(value[0].casefold(),value[1]) if kind=='SRV' else value.casefold()
                        key=(name.casefold(),kind,normalized)
                        if ttl:records[key]=(now+ttl,(name,kind,value))
                        else:records.pop(key,None)  # A goodbye is not a fresh device.
                    for item in advertised_candidates([record for expires,record in records.values() if expires>now]):
                        observed[item['candidate_id']]=item
                except (ValueError,UnicodeError,struct.error):continue
                if len(records)>=512:break
    except OSError:state='unavailable'
    now=clock()
    live=[record for expires,record in records.values() if expires>now]
    candidates=advertised_candidates(live) if state=='completed' else []
    # Never extend an advertisement's TTL or present an old search as live.
    for candidate in candidates:
        instance=candidate['service_instance'].casefold();host=candidate['hostname']
        required=[expires for expires,(name,kind,value) in records.values() if expires>now and (
            (kind=='PTR' and name.casefold() in SERVICES and value.casefold()==instance)
            or (kind=='SRV' and name.casefold()==instance and value[0].casefold()==host and value[1]==candidate['endpoint']['port'])
            or (kind=='A' and name.casefold()==host and value==candidate['address'] and candidate['address']!=host))]
        candidate['valid_for_seconds']=min(30.,max(0,min(required,default=now)-now))
        candidate['_expires_monotonic']=now+candidate['valid_for_seconds']
    current_ids={item['candidate_id'] for item in candidates}
    return candidates,{'state':state,'scope':'advertised_mdns_only','services':list(SERVICES),'identity_verified':False,
        '_expired_candidates':[item for key,item in observed.items() if key not in current_ids]}


def known_os_devices():
    from .robot_registry import enumerate_windows_devices
    serial=enumerate_windows_devices();candidates=serial['candidates'][:64]
    bluetooth='unavailable'
    if os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Services\BTHPORT\Parameters\Devices') as devices:
                for index in range(min(winreg.QueryInfoKey(devices)[0],64)):
                    address=winreg.EnumKey(devices,index)
                    if not re.fullmatch('[a-fA-F0-9]{12}',address):continue
                    label='Known Bluetooth device'
                    try:
                        with winreg.OpenKey(devices,address) as device:
                            name,_=winreg.QueryValueEx(device,'Name')
                            if isinstance(name,bytes):name=name.rstrip(b'\0').decode('utf-8',errors='replace')
                            if isinstance(name,str) and name.strip() and not any(ord(c)<32 for c in name):label=name[:80]
                    except OSError:pass
                    formatted=':'.join(address[i:i+2] for i in range(0,12,2)).upper()
                    candidates.append({'candidate_id':hashlib.sha256(('bluetooth:'+address).encode()).hexdigest(),
                                       'transport':'bluetooth','address':formatted,'label':label,'identity_verified':False,'adapter_id':None})
            bluetooth='os_known_devices'
        except FileNotFoundError:bluetooth='os_known_devices'
        except OSError:bluetooth='access_unavailable'
    return candidates,{'serial':{'state':serial['serial_state'],'scope':'os_known_devices_no_open'},
                       'bluetooth':{'state':bluetooth,'scope':'os_known_devices_no_pairing_or_radio_probe'}}


def discover():
    known,sources=known_os_devices()
    network,source=advertised_network();sources['network']=source
    return {'candidates':network[:64],'known_devices':known[:64],
        'expired_candidates':source.pop('_expired_candidates',[])[:64],'sources':sources}
