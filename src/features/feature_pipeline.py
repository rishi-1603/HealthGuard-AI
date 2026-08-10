import json
from pathlib import Path
import pandas as pd

def bundle_to_frame(path='data/synthetic/bundle.json'):
    data = json.loads(Path(path).read_text())
    
    patients = {}
    obs = {}
    encounters = {}
    conditions = {}
    
    for e in data['entry']:
        r = e['resource']
        t = r['resourceType']
        
        if t == 'Patient':
            pid = r['id']
            # Default fallback values for region and insurance if not generated
            region = next((ext['valueString'] for ext in r.get('extension', []) if ext['url'].endswith('region')), 'Unknown')
            insurance = next((ext['valueString'] for ext in r.get('extension', []) if ext['url'].endswith('insurance')), 'Unknown')
            patients[pid] = {
                'patient_id': pid,
                'gender': r.get('gender'),
                'age': 2026 - int(r['birthDate'][:4]),
                'region': region,
                'insurance': insurance
            }
        elif t == 'Observation':
            pid = r['subject']['reference'].split('/')[-1]
            code = r['code']['text']
            val = r['valueQuantity']['value']
            if pid not in obs:
                obs[pid] = {'heart-rate': [], 'systolic-bp': [], 'spo2': []}
            if code in obs[pid]:
                obs[pid][code].append(val)
        elif t == 'Encounter':
            pid = r['subject']['reference'].split('/')[-1]
            encounters[pid] = encounters.get(pid, 0) + 1
        elif t == 'Condition':
            pid = r['subject']['reference'].split('/')[-1]
            conditions[pid] = r['code']['text']

    rows = []
    for pid, p in patients.items():
        p_obs = obs.get(pid, {'heart-rate': [80], 'systolic-bp': [120], 'spo2': [98]})
        
        hr = p_obs['heart-rate'] if p_obs['heart-rate'] else [80]
        sbp = p_obs['systolic-bp'] if p_obs['systolic-bp'] else [120]
        spo2 = p_obs['spo2'] if p_obs['spo2'] else [98]
        
        abnormal_count = sum(v > 100 or v < 55 for v in hr) + sum(v > 140 for v in sbp) + sum(v < 90 for v in spo2)
        
        row = {
            **p,
            'observation_count': len(hr) + len(sbp) + len(spo2),
            'latest_heart_rate': hr[-1],
            'mean_heart_rate': sum(hr) / len(hr),
            'mean_systolic_bp': sum(sbp) / len(sbp),
            'spo2_min': min(spo2),
            'abnormal_count': abnormal_count,
            'trend': hr[-1] - hr[0],
            'encounter_count': encounters.get(pid, 0),
            'condition': conditions.get(pid, 'none')
        }
        
        # New target: is high risk if they have multiple encounters AND multiple abnormal vitals OR very low SpO2
        is_high_risk = int(
            (row['encounter_count'] > 3 and row['abnormal_count'] > 5) or 
            row['spo2_min'] < 90 or
            row['mean_systolic_bp'] > 160
        )
        row['risk_target'] = is_high_risk
        
        rows.append(row)
        
    return pd.DataFrame(rows)
