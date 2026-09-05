"""Strict reader and surgical lobby repair for locally observed ESAV v3 profiles.

Only lobby map entries and the NbIA preference are edited. Unreferenced objects
are retained so every existing object ID, deck and statistics record survives.
"""
from dataclasses import dataclass
from compression import zstd
import struct
import zlib

def u32(data, at=0): return struct.unpack_from('<I',data,at)[0]
def p32(value): return struct.pack('<I',value)
def require(ok,message):
    if not ok: raise ValueError(message)

@dataclass
class Value:
    kind:int
    data:object
    start:int
    end:int

class Ndf:
    def __init__(self,raw):
        self.raw=raw
        self.toc=raw.rfind(b'TOC0')
        require(self.toc>=0,'Missing NDF section table')
        count=u32(raw,self.toc+4)
        require(count==9 and self.toc+8+24*count==len(raw),'Unknown NDF table layout')
        self.sections={}
        for i in range(count):
            at=self.toc+8+i*24
            name=raw[at:at+4].decode('ascii')
            start,size=struct.unpack_from('<QQ',raw,at+8)
            require(start>=40 and start-40+size<=self.toc,'Invalid NDF section')
            self.sections[name]=(start-40,size)
        self.classes=self.strings('CLAS')
        self.string_table=self.strings('STRG')
        data=self.section('PROP');pos=0;self.properties=[]
        while pos<len(data):
            leng=u32(data,pos);pos+=4
            name=data[pos:pos+leng].decode();pos+=leng
            cls=u32(data,pos);pos+=4
            self.properties.append((cls,name))
        self.objects=[]
        pos,size=self.sections['OBJE'];stop=pos+size
        while pos<stop:
            start=pos;cls=u32(raw,pos);pos+=4
            require(cls<len(self.classes),'Unknown NDF object class')
            props={}
            while True:
                prop=u32(raw,pos);pos+=4
                if prop==0xabababab:break
                require(prop<len(self.properties),'Unknown NDF property')
                val=self.value(pos);pos=val.end
                require(prop not in props,'Duplicate NDF property')
                props[prop]=val
            self.objects.append({'class':cls,'properties':props,'start':start,'end':pos})
        require(pos==stop,'NDF object parse boundary mismatch')

    def section(self,name):
        start,size=self.sections[name];return self.raw[start:start+size]
    def strings(self,name):
        b=self.section(name);pos=0;out=[]
        while pos<len(b):
            leng=u32(b,pos);pos+=4
            require(pos+leng<=len(b),'String boundary mismatch')
            out.append(b[pos:pos+leng].decode('utf-8'));pos+=leng
        return out
    def value(self,pos):
        start=pos;kind=u32(self.raw,pos);pos+=4
        if kind==9:
            subtype=u32(self.raw,pos);pos+=4
            if subtype==0xbbbbbbbb:
                val=struct.unpack_from('<II',self.raw,pos);pos+=8
            elif subtype==0xaaaaaaaa:val=u32(self.raw,pos);pos+=4
            elif subtype==0xabababab:val=None
            else:raise ValueError(f'Unknown NDF reference {subtype:x}')
            val=(subtype,val)
        elif kind in (0x11,0x12):
            count=u32(self.raw,pos);pos+=4;val=[]
            require(count<=100000,'Unreasonable NDF collection')
            for _ in range(count):
                left=self.value(pos);pos=left.end
                if kind==0x12:
                    right=self.value(pos);pos=right.end;val.append((left,right))
                else:val.append(left)
        elif kind==0x22:
            left=self.value(pos);right=self.value(left.end);pos=right.end;val=(left,right)
        elif kind in (8,0x14):
            size=u32(self.raw,pos);pos+=4;val=self.raw[pos:pos+size];pos+=size
        else:
            sizes={0:1,1:1,2:4,3:4,4:8,5:4,6:8,7:4,0xb:12,0xc:16,0xd:4,0xe:12,0x18:2,0x19:2,0x1a:16,0x1c:4,0x1d:8,0x1f:8,0x21:8,0x25:16,0xabababab:0}
            require(kind in sizes,f'Unknown NDF value type {kind:x} at {start:x}')
            size=sizes[kind];val=self.raw[pos:pos+size];pos+=size
            if kind in (0,1,2,3,7,0x1c):val=int.from_bytes(val,'little',signed=kind==2)
        require(pos<=self.sections['OBJE'][0]+self.sections['OBJE'][1],'NDF value outside objects')
        return Value(kind,val,start,pos)
    def prop(self,obj,name):
        found=[val for pid,val in obj['properties'].items() if self.properties[pid][1]==name]
        require(len(found)<=1,'Ambiguous NDF property')
        return found[0] if found else None
    def object_of_class(self,name):
        return [obj for obj in self.objects if self.classes[obj['class']]==name]
    def rebuild(self,changes):
        out=bytearray();entries=[]
        for name,(start,size) in self.sections.items():
            content=changes.get(name,self.raw[start:start+size])
            entries.append(name.encode()+b'\0'*4+struct.pack('<QQ',len(out)+40,len(content)))
            out.extend(content)
        out.extend(b'TOC0'+p32(len(entries))+b''.join(entries))
        return bytes(out)

class Profile:
    def __init__(self,data):
        self.data=data
        require(data[:8]==b'ESAV\0\0\0\3','Unsupported profile header')
        require(int.from_bytes(data[8:12],'big')==len(data),'Profile size mismatch')
        require(u32(data,12)==zlib.adler32(data[16:],0),'Profile checksum mismatch')
        self.chunks=[];pos=16
        while pos<len(data):
            tag=data[pos:pos+4];size=int.from_bytes(data[pos+4:pos+12],'big')
            flags=data[pos+12:pos+16];end=pos+16+size
            require(end<=len(data),'Profile chunk size mismatch')
            self.chunks.append((tag,flags,data[pos+16:end]));pos=end
        require(pos==len(data),'Profile trailing bytes')
        mains=[i for i,(tag,_,_) in enumerate(self.chunks) if tag==b'sama']
        require(len(mains)==1,'Missing profile data chunk');self.main_index=mains[0]
        b=self.chunks[self.main_index][2];count=u32(b);pos=4;self.records=[]
        for _ in range(count):
            leng=u32(b,pos);pos+=4;name=b[pos:pos+leng].decode();pos+=leng
            size=u32(b,pos);pos+=4;record=b[pos:pos+size];pos+=size
            require(record[:8]==b'EUG0\1\0\0\0' and record[8:12]==b'CNDF','Unsupported embedded NDF')
            flag=u32(record,12)
            if flag==2:
                require(record[44:48]==bytes.fromhex('28b52ffd'),'Unsupported NDF compression')
                raw=zstd.decompress(record[44:])
                require(u32(record,40)==len(raw),'Decompressed NDF size mismatch')
            elif flag==0:raw=record[40:]
            else:raise ValueError('Unsupported NDF flags')
            require(struct.unpack_from('<Q',record,32)[0]==len(raw)+40,'NDF size mismatch')
            require(struct.unpack_from('<Q',record,16)[0]==raw.rfind(b'TOC0')+40,'NDF TOC mismatch')
            self.records.append((name,record,raw))
        require(pos==len(b),'Profile record boundary mismatch')
    def rebuild(self,raw_changes):
        records=[]
        for name,record,raw in self.records:
            if name in raw_changes:
                raw=raw_changes[name];head=bytearray(record[:40])
                struct.pack_into('<I',head,12,2)
                struct.pack_into('<Q',head,16,raw.rfind(b'TOC0')+40)
                struct.pack_into('<Q',head,32,len(raw)+40)
                record=bytes(head)+p32(len(raw))+zstd.compress(raw,level=3)
            encoded=name.encode();records.append(p32(len(encoded))+encoded+p32(len(record))+record)
        main=p32(len(records))+b''.join(records);chunks=[]
        for i,(tag,flags,payload) in enumerate(self.chunks):
            if i==self.main_index:payload=main
            chunks.append(tag+len(payload).to_bytes(8,'big')+flags+payload)
        body=b''.join(chunks)
        return self.data[:8]+(len(body)+16).to_bytes(4,'big')+p32(zlib.adler32(body,0))+body

def repair(data):
    profile=Profile(data);changes={};details={}
    player_team=0
    for _,_,record_raw in profile.records:
        prefs_ndf=Ndf(record_raw)
        for obj in prefs_ndf.object_of_class('TAdditionalDataPlayerProfileAddLobbyPreferences'):
            local=prefs_ndf.prop(obj,'SkirmishPreferences_LocalPlayerInfo')
            if local:
                require(local.kind==0x12,'Unexpected local-player preferences')
                for key,val in local.data:
                    if key.kind==7 and prefs_ndf.string_table[key.data]=='PlayerAlliance':
                        require(val.kind==7,'Unexpected player alliance type')
                        player_team=int(prefs_ndf.string_table[val.data])
    require(player_team in (0,1),'Unknown player alliance')
    details['player_alliance']=player_team
    main_records=[(name,raw) for name,_,raw in profile.records if name=='Profile']
    require(len(main_records)==1,'Missing main profile record')
    name,raw=main_records[0];ndf=Ndf(raw)
    configs=[obj for obj in ndf.object_of_class('TLobbyIAConfig') if ndf.prop(obj,'IAConfigs')]
    require(len(configs)==1,'Ambiguous lobby configuration')
    value=ndf.prop(configs[0],'IAConfigs')
    require(value and value.kind==0x12,'Missing lobby AI map')
    details['saved_ai_configs']=len(value.data)
    chosen=[];team_counts={0:0,1:0}
    # Leave space for the human on their actual saved alliance.
    for key,ref in value.data:
        require(key.kind==3 and ref.kind==9 and ref.data[0]==0xbbbbbbbb,'Unexpected lobby AI entry')
        oid,cls=ref.data[1];obj=ndf.objects[oid]
        require(obj['class']==cls and ndf.classes[cls]=='TLobbyOneIAConfig','Invalid AI object reference')
        alliance=ndf.prop(obj,'IAAlliance');team=alliance.data if alliance else 0
        require(team in (0,1),'Unknown AI alliance')
        cap=3 if team==player_team else 4
        if team_counts[team]<cap:
            team_counts[team]+=1;chosen.append((key,ref))
    # Never reinterpret a vanilla-sized saved lobby: older valid profiles can
    # retain alliance choices that the game normalizes when opening the lobby.
    if len(value.data)>7:
        chosen.sort(key=lambda pair:(ndf.prop(ndf.objects[pair[1].data[1][0]],'IAAlliance').data if ndf.prop(ndf.objects[pair[1].data[1][0]],'IAAlliance') else 0))
        replacement=p32(0x12)+p32(len(chosen))
        for i,(_,ref) in enumerate(chosen):replacement+=p32(3)+p32(i)+raw[ref.start:ref.end]
        start,size=ndf.sections['OBJE']
        obj_section=raw[start:value.start]+replacement+raw[value.end:start+size]
        changes[name]=ndf.rebuild({'OBJE':obj_section})
        details['retained_ai_configs']=len(chosen)
    else:details['retained_ai_configs']=len(value.data)

    for name,_,raw in profile.records:
        ndf=Ndf(raw)
        prefs=ndf.object_of_class('TAdditionalDataPlayerProfileAddLobbyPreferences')
        if not prefs:continue
        require(len(prefs)==1,'Ambiguous lobby preferences')
        value=ndf.prop(prefs[0],'SkirmishPreferences_MatchInfo')
        require(value and value.kind==0x12,'Missing skirmish preferences')
        entries=[(k,v) for k,v in value.data if k.kind==7 and ndf.string_table[k.data]=='NbIA']
        require(len(entries)==1,'Missing saved AI count')
        _,v=entries[0];require(v.kind==7,'Unexpected saved AI count type')
        old_count=int(ndf.string_table[v.data]);details['saved_ai_count']=old_count
        if old_count>7 or ('Profile' in changes and old_count!=details['retained_ai_configs']):
            # Append a new string and retarget only this value, since a string
            # table entry could be shared by unrelated options.
            text=str(details['retained_ai_configs']).encode()
            new_strings=ndf.section('STRG')+p32(len(text))+text
            objs=bytearray(ndf.section('OBJE'))
            struct.pack_into('<I',objs,v.start-ndf.sections['OBJE'][0]+4,len(ndf.string_table))
            changes[name]=ndf.rebuild({'OBJE':bytes(objs),'STRG':new_strings})
    if not changes:return data,details
    repaired=profile.rebuild(changes)
    check=Profile(repaired)
    for name,_,raw in check.records:Ndf(raw)
    # All records other than the two explicitly changed remain byte-identical.
    for before,after in zip(profile.records,check.records):
        if before[0] not in changes:require(before==after,'Unrelated profile record changed')
    # Existing object payloads retain their IDs and bytes; only the IAConfigs
    # property may differ in the main profile.
    new_main=Ndf(next(raw for name,_,raw in check.records if name=='Profile'))
    old_main=Ndf(main_records[0][1])
    require(len(new_main.objects)==len(old_main.objects),'An existing profile object was removed')
    for old_obj,new_obj in zip(old_main.objects,new_main.objects):
        require(old_obj['class']==new_obj['class'],'Existing object identity changed')
        for pid,old_val in old_obj['properties'].items():
            if old_main.classes[old_obj['class']]=='TLobbyIAConfig' and old_main.properties[pid][1]=='IAConfigs':continue
            new_val=new_obj['properties'][pid]
            require(old_main.raw[old_val.start:old_val.end]==new_main.raw[new_val.start:new_val.end],'Unrelated profile property changed')
    details['changed_records']=list(changes)
    return repaired,details

if __name__=='__main__':
    import sys,json
    from pathlib import Path
    path=Path(sys.argv[1]);fixed,report=repair(path.read_bytes());print(json.dumps(report,indent=2))
    if len(sys.argv)>2:Path(sys.argv[2]).write_bytes(fixed)
