"""Fallback-safe RAG/LLM interface. Uses keyword retrieval and mock answers without keys."""
from pathlib import Path

def retrieve(query:str, k:int=3):
 docs=[]
 for p in Path('knowledge_base/documents').glob('*.md'):
  text=p.read_text(); score=sum(w.lower() in text.lower() for w in query.split())
  docs.append((score,p.name,text[:500]))
 return [{'source':n,'text':t} for s,n,t in sorted(docs,reverse=True)[:k]]

def answer(query:str, context:dict|None=None):
 evidence=retrieve(query)
 return {'answer':f'Demonstration summary: {query}. Review the risk factors and recent trends with a qualified clinician.', 'evidence':evidence, 'mode':'mock' if not __import__('os').getenv('LLM_API_KEY') else 'configured-provider'}
