import json
from pathlib import Path
import pandas as pd

def bundle_to_frame(path='data/synthetic/bundle.json'):
 data=json.loads(Path(path).read_text()); patients={}; obs={}
 for e in data['entry']:
  r=e['resource']; t=r['resourceType']
  if t=='Patient': patients[r['id']]={'patient_id':r['id'],'gender':r.get('gender'),'age':2026-int(r['birthDate'][:4])}
  elif t=='Observation':
   pid=r['subject']['reference'].split('/')[-1]; obs.setdefault(pid,[]).append(r['valueQuantity']['value'])
 rows=[]
 for pid,p in patients.items():
  x=obs.get(pid, [80]); rows.append({**p,'observation_count':len(x),'latest_heart_rate':x[-1],'mean_heart_rate':sum(x)/len(x),'abnormal_count':sum(v>100 or v<55 for v in x),'trend':x[-1]-x[0],'risk_target':int(sum(v>100 or v<55 for v in x)>=2 or p['age']>70)})
 return pd.DataFrame(rows)
