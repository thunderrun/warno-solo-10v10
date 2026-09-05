"""Generate synthetic ESAV/CNDF fixtures; no player's profile is distributed."""
import struct
import zlib
from profile_codec import p32

def strings(values):
    return b''.join(p32(len(v.encode()))+v.encode() for v in values)

def value_int(value):return p32(3)+p32(value)
def value_string(index):return p32(7)+p32(index)
def value_ref(oid,cls):return p32(9)+p32(0xbbbbbbbb)+p32(oid)+p32(cls)
def value_map(pairs):return p32(0x12)+p32(len(pairs))+b''.join(a+b for a,b in pairs)
def obj(cls,props):return p32(cls)+b''.join(p32(pid)+v for pid,v in props)+p32(0xabababab)

def ndf_record(classes,properties,table,objects):
    sections={
        'OBJE':b''.join(objects),'TOPO':b'','CHNK':b'',
        'CLAS':strings(classes),
        'PROP':b''.join(strings([name])+p32(cls) for cls,name in properties),
        'STRG':strings(table),'TRAN':b'','IMPR':b'','EXPR':b'',
    }
    raw=bytearray();toc=[]
    for name,data in sections.items():
        toc.append(name.encode()+b'\0'*4+struct.pack('<QQ',len(raw)+40,len(data)))
        raw.extend(data)
    offset=len(raw)+40
    raw.extend(b'TOC0'+p32(9)+b''.join(toc))
    return b'EUG0'+p32(1)+b'CNDF'+p32(0)+struct.pack('<QQQ',offset,40,len(raw)+40)+raw

def profile(nato=9,pact=10,player=0,saved_count=None):
    count=nato+pact
    ais=value_map([(value_int(i),value_ref(i+1,1)) for i in range(count)])
    objects=[obj(0,[(0,ais)])]
    objects += [obj(1,[(1,value_int(team))]) for team in [0]*nato+[1]*pact]
    # A synthetic unrelated object acts as a preservation canary.
    marker=b'Synthetic unrelated deck and statistics payload'
    objects.append(obj(2,[(2,p32(0x14)+p32(len(marker))+marker)]))
    main=ndf_record(['TLobbyIAConfig','TLobbyOneIAConfig','SyntheticDeck'],
                    [(0,'IAConfigs'),(1,'IAAlliance'),(2,'Payload')],[],objects)
    prefs=ndf_record(['TAdditionalDataPlayerProfileAddLobbyPreferences'],
                    [(0,'SkirmishPreferences_MatchInfo'),(0,'SkirmishPreferences_LocalPlayerInfo')],
                    ['NbIA',str(count if saved_count is None else saved_count),'PlayerAlliance',str(player)],
                    [obj(0,[(0,value_map([(value_string(0),value_string(1))])),
                            (1,value_map([(value_string(2),value_string(3))]))])])
    untouched=ndf_record(['SyntheticStats'],[(0,'Value')],[],[obj(0,[(0,value_int(12345))])])
    records=[('Profile',main),('Profile_Additional_4',prefs),('SyntheticStatistics',untouched)]
    payload=p32(len(records))+b''.join(strings([name])+p32(len(record))+record for name,record in records)
    body=b'sama'+len(payload).to_bytes(8,'big')+b'\0'*4+payload
    return b'ESAV\0\0\0\3'+(len(body)+16).to_bytes(4,'big')+p32(zlib.adler32(body,0))+body
