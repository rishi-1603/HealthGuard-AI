import json
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)

OUT = Path('data/synthetic')
OUT.mkdir(parents=True, exist_ok=True)

entries = []
num_patients = 500

for i in range(1, num_patients + 1):
    pid = f'P{i:04d}'
    age = random.randint(18, 88)
    today = date(2026, 1, 1)
    
    # Patient Demographics
    gender = random.choice(['male', 'female'])
    region = random.choice(['North', 'South', 'East', 'West'])
    insurance = random.choice(['Medicare', 'Medicaid', 'Private', 'None'])
    
    entries.append({
        'resource': {
            'resourceType': 'Patient',
            'id': pid,
            'gender': gender,
            'birthDate': str(date(today.year - age, random.randint(1, 12), random.randint(1, 28))),
            'extension': [
                {'url': 'http://example.org/fhir/StructureDefinition/region', 'valueString': region},
                {'url': 'http://example.org/fhir/StructureDefinition/insurance', 'valueString': insurance}
            ]
        }
    })
    
    # Time-series observations (30 days)
    num_days = random.randint(30, 90)
    for j in range(num_days):
        obs_date = today - timedelta(days=num_days - j)
        
        # Risk factors influence vitals
        is_high_risk = age > 65 and random.random() < 0.3
        
        # Heart rate
        hr_val = random.gauss(105 if is_high_risk else 78, 12)
        entries.append({
            'resource': {
                'resourceType': 'Observation',
                'id': f'O_HR_{i:04d}_{j}',
                'status': 'final',
                'subject': {'reference': f'Patient/{pid}'},
                'effectiveDateTime': str(obs_date),
                'code': {'text': 'heart-rate'},
                'valueQuantity': {'value': round(hr_val, 1), 'unit': 'bpm'}
            }
        })
        
        # Systolic BP
        sbp_val = random.gauss(140 if is_high_risk else 120, 15)
        entries.append({
            'resource': {
                'resourceType': 'Observation',
                'id': f'O_SBP_{i:04d}_{j}',
                'status': 'final',
                'subject': {'reference': f'Patient/{pid}'},
                'effectiveDateTime': str(obs_date),
                'code': {'text': 'systolic-bp'},
                'valueQuantity': {'value': round(sbp_val, 1), 'unit': 'mmHg'}
            }
        })
        
        # SpO2
        spo2_val = random.gauss(92 if is_high_risk else 98, 2)
        spo2_val = min(100, max(80, spo2_val))
        entries.append({
            'resource': {
                'resourceType': 'Observation',
                'id': f'O_SPO2_{i:04d}_{j}',
                'status': 'final',
                'subject': {'reference': f'Patient/{pid}'},
                'effectiveDateTime': str(obs_date),
                'code': {'text': 'spo2'},
                'valueQuantity': {'value': round(spo2_val, 1), 'unit': '%'}
            }
        })

    # Encounters
    encounter_count = random.randint(1, 5 if is_high_risk else 2)
    for k in range(encounter_count):
        entries.append({
            'resource': {
                'resourceType': 'Encounter',
                'id': f'E{i:04d}_{k}',
                'status': 'finished',
                'subject': {'reference': f'Patient/{pid}'},
                'period': {'start': str(today - timedelta(days=random.randint(5, 90)))}
            }
        })
        
    # Condition
    condition = random.choice(['hypertension', 'diabetes', 'asthma', 'none'])
    entries.append({
        'resource': {
            'resourceType': 'Condition',
            'id': f'C{i:04d}',
            'subject': {'reference': f'Patient/{pid}'},
            'code': {'text': condition}
        }
    })
    
    # Medication
    entries.append({
        'resource': {
            'resourceType': 'MedicationRequest',
            'id': f'M{i:04d}',
            'status': 'active',
            'subject': {'reference': f'Patient/{pid}'},
            'medicationCodeableConcept': {'text': 'standard medication'}
        }
    })

bundle = {'resourceType': 'Bundle', 'type': 'collection', 'entry': entries}
(OUT / 'bundle.json').write_text(json.dumps(bundle, indent=2))
print(f'generated {len(entries)} FHIR resources -> {OUT}/bundle.json')
