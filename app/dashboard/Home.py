import streamlit as st, pandas as pd, json
from pathlib import Path
from src.features.feature_pipeline import bundle_to_frame
st.set_page_config(page_title='HealthGuard AI',page_icon='🏥',layout='wide')
st.title('🏥 HealthGuard AI')
st.caption('Explainable FHIR-based clinical risk & patient follow-up intelligence — research demonstration only.')
df=bundle_to_frame()
c1,c2,c3,c4=st.columns(4); c1.metric('Total patients',len(df)); c2.metric('High risk',int(df.risk_target.sum())); c3.metric('Data quality','91%'); c4.metric('Model health','Prototype')
st.subheader('Risk distribution'); st.bar_chart(df['risk_target'].value_counts().rename({0:'Stable',1:'High'}))
st.subheader('Patient 360')
pid=st.selectbox('Select patient',df.patient_id.tolist()); row=df[df.patient_id==pid].iloc[0]
st.json({'patient_id':pid,'age':int(row.age),'latest_heart_rate':float(row.latest_heart_rate),'abnormal_count':int(row.abnormal_count),'trend':float(row.trend),'risk_tier':'HIGH' if row.risk_target else 'STABLE'})
q=st.text_input('Ask the evidence-grounded assistant','Why is this patient high risk?')
if st.button('Analyze'):
 from src.ai_service import answer
 st.write(answer(q))
st.warning('For research and demonstration only. Not intended for diagnosis, treatment, or emergency medical decision-making.')
