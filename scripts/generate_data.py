import json, random
from datetime import date, timedelta
from pathlib import Path
random.seed(7)
OUT=Path('data/synthetic'); OUT.mkdir(parents=True, exist_ok=True)
entries=[]
for i in range(1,101):
 pid=f'P{i:04d}'; age=random.randint(18,88); today=date(2026,1,1)
 entries.append({'resource':{'resourceType':'Patient','id':pid,'gender':random.choice(['male','female']),'birthDate':str(date(today.year-age,random.randint(1,12),random.randint(1,28)))}})
 for j in range(5):
  val= random.gauss(105 if random.random()<.25 else 78,12)
  entries.append({'resource':{'resourceType':'Observation','id':f'O{i:04d}_{j}','status':'final','subject':{'reference':f'Patient/{pid}'},'effectiveDateTime':str(today-timedelta(days=4-j)),'code':{'text':'heart-rate'},'valueQuantity':{'value':round(val,1),'unit':'bpm'}}})
 entries.append({'resource':{'resourceType':'Encounter','id':f'E{i:04d}','status':'finished','subject':{'reference':f'Patient/{pid}'},'period':{'start':str(today-timedelta(days=random.randint(5,90)))}}})
 entries.append({'resource':{'resourceType':'Condition','id':f'C{i:04d}','subject':{'reference':f'Patient/{pid}'},'code':{'text':random.choice(['hypertension','diabetes','asthma','none'])}}})
 entries.append({'resource':{'resourceType':'MedicationRequest','id':f'M{i:04d}','status':'active','subject':{'reference':f'Patient/{pid}'},'medicationCodeableConcept':{'text':'standard medication'}}})
bundle={'resourceType':'Bundle','type':'collection','entry':entries}
(OUT/'bundle.json').write_text(json.dumps(bundle,indent=2)); print(f'generated {len(entries)} FHIR resources -> {OUT}/bundle.json')
