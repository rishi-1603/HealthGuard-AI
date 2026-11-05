import json
import math
import pytest

from app.dashboard.utils import decision_history as h


def snapshot():
 return {'schema_version':1,'project':'hospital_operations','source':{},'evidence':{},'assumptions':{},'scenarios':{},'decision':{'action':'Review cases','status':'proposed'},'scope':{'eligible_customers':5},'observed_outcome':None}


def test_export_import_and_user_entered_followup():
 history=h.new_history('hospital_operations')
 history=h.add_snapshot(history,snapshot())
 assert len(history['entries'])==1
 entry_id=history['entries'][0]['id']
 history=h.add_followup(history,entry_id,metric='Verified review outcomes',unit='cases',baseline=1,observed=3,observed_date='2026-11-05',note='Source to be checked')
 f=history['entries'][0]['followups'][0]
 assert f['difference']==2 and f['verification']=='user-entered, unverified'
 restored=h.import_history(h.export_history(history),'hospital_operations')
 assert restored['entries'][0]['followups'][0]['difference']==2
 assert restored['trust']=='imported, unverified'


def test_rejects_wrong_project_corrupt_and_invalid_numbers():
 history=h.add_snapshot(h.new_history('hospital_operations'),snapshot())
 with pytest.raises(ValueError): h.import_history(h.export_history(history),'refund_risk')
 with pytest.raises(ValueError): h.import_history(b'{bad','hospital_operations')
 with pytest.raises(ValueError): h.import_history(b'{"schema_version":1,"project":"hospital_operations","entries":NaN}','hospital_operations')
 with pytest.raises(ValueError): h.add_followup(history,history['entries'][0]['id'],metric='x',unit='cases',baseline=0,observed=math.inf,observed_date='2026-11-05',note='')


def test_duplicate_entries_oversize_and_date_are_refused():
 history=h.add_snapshot(h.new_history('hospital_operations'),snapshot())
 history['entries'].append(history['entries'][0].copy())
 with pytest.raises(ValueError): h.import_history(json.dumps(history).encode(),'hospital_operations')
 with pytest.raises(ValueError): h.import_history(b'x'*300000,'hospital_operations')
 history=h.add_snapshot(h.new_history('hospital_operations'),snapshot())
 with pytest.raises(ValueError): h.add_followup(history,history['entries'][0]['id'],metric='x',unit='x',baseline=None,observed=2,observed_date='not-date',note='')


def test_snapshot_is_copied_and_history_has_limit():
 record=snapshot();history=h.add_snapshot(h.new_history('hospital_operations'),record);record['decision']['action']='changed'
 assert history['entries'][0]['record']['decision']['action']=='Review cases'
 for _ in range(29):history=h.add_snapshot(history,snapshot())
 with pytest.raises(ValueError):h.add_snapshot(history,snapshot())


def test_import_rejects_record_without_evidence_and_forged_verification():
 record=snapshot()
 record.update({'source':{},'evidence':{},'assumptions':{},'scenarios':{}})
 history=h.add_snapshot(h.new_history('hospital_operations'),record)
 entry=history['entries'][0]
 entry['record'].pop('evidence')
 with pytest.raises(ValueError):h.import_history(json.dumps(history).encode(),'hospital_operations')


def test_duplicate_json_keys_are_rejected():
 raw=b'{"schema_version":1,"project":"hospital_operations","project":"hospital_operations","entries":[]}'
 with pytest.raises(ValueError):h.import_history(raw,'hospital_operations')


def test_noncanonical_observation_date_is_rejected():
 history=h.add_snapshot(h.new_history('hospital_operations'),snapshot())
 with pytest.raises(ValueError):
  h.add_followup(history,history['entries'][0]['id'],metric='x',unit='cases',baseline=0,observed=1,observed_date='20261105',note='')
