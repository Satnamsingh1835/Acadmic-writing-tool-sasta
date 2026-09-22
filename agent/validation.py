from __future__ import annotations
from collections import Counter
import re
from .models import EVIDENCE_LEVELS

class Validator:
 def validate_sources(self,sources):
  issues=[]
  counts=Counter(s.source_id for s in sources)
  for sid,n in counts.items():
   if n>1: issues.append({"type":"DUPLICATE_SOURCE","source_id":sid,"severity":"error"})
  seen={}
  for s in sources:
   if not s.evidence: issues.append({"type":"MISSING_TRACEABILITY","source_id":s.source_id,"severity":"error"})
   key=(s.author.lower(),s.year) if s.author and s.year else None
   if key and key in seen and seen[key]!=s.source_id:
    issues.append({"type":"CONTRADICTORY_METADATA","source_ids":[seen[key],s.source_id],"field":"author/year","severity":"warning"})
   if key: seen[key]=s.source_id
   for q in s.quotations:
    if not q.get("page"): issues.append({"type":"QUOTE_MISSING_PAGE","source_id":s.source_id,"severity":"warning"})
  return issues

 def validate_claims(self,claims):
  issues=[]
  for c in claims:
   if c.evidence_level not in EVIDENCE_LEVELS: issues.append({"type":"INVALID_EVIDENCE_LEVEL","claim":c.claim})
   if c.evidence_level in {"A","B","C"} and not c.source_ids: issues.append({"type":"UNSUPPORTED_CLAIM","claim":c.claim})
   if any(not isinstance(p,int) or p<1 for p in c.pages): issues.append({"type":"INVALID_PAGE","claim":c.claim})
   if c.evidence_level=="A" and not c.snippets: issues.append({"type":"DIRECT_EVIDENCE_WITHOUT_SNIPPET","claim":c.claim})
   if c.evidence_level in {"D","E"} and c.status=="supported": issues.append({"type":"UNLABELLED_ANALYTICAL_POSSIBILITY","claim":c.claim})
  return issues

 def audit_text(self,text,sources):
  known={s.source_id for s in sources}; issues=[]
  for m in re.finditer(r"\[([A-Za-z0-9_-]+)(?:\s+p\.\s*(\d+))?\]",text):
   sid,page=m.group(1),m.group(2)
   if sid not in known: issues.append({"type":"CITATION_MISMATCH","citation":m.group(0)})
   elif page and not any(e.get("page")==int(page) for s in sources if s.source_id==sid for e in s.evidence):
    issues.append({"type":"PAGE_MISMATCH","citation":m.group(0)})
  for m in re.finditer(r"\b(proves?|demonstrates?|always|never|all|none|causes?)\b",text,re.I):
   issues.append({"type":"POSSIBLE_OVERCLAIM","term":m.group(0),"position":m.start()})
  if len(known)>1 and not re.search(r"\b(however|whereas|while|in contrast|similarly|extends?|qualifies?|complicates?|varies?|tension)\b",text,re.I):
   issues.append({"type":"SUMMARY_WITHOUT_SYNTHESIS","severity":"warning"})
  return issues

 def validate_gaps(self,gaps):
  issues=[]
  for g in gaps:
   if not g.source_ids: issues.append({"type":"GAP_WITHOUT_SOURCE","statement":g.statement,"severity":"error"})
   if g.gap_type=="RELATIONAL" and g.evidence_level!="D": issues.append({"type":"RELATIONAL_GAP_REQUIRES_VERIFICATION","statement":g.statement,"severity":"warning"})
  return issues

 def validate_concepts(self,sources):
  issues=[]; grouped={}
  for s in sources:
   for d in s.definitions:
    c=d.get("concept","").lower(); grouped.setdefault(c,[]).append(d.get("definition",""))
  for c,defs in grouped.items():
   if len(set(defs))>1: issues.append({"type":"CONCEPTUAL_VARIATION","concept":c,"definitions":defs,"severity":"warning"})
  return issues

 def quality_report(self,sources,claims,gaps=None,text=""):
  gaps=gaps or []
  return {"source_issues":self.validate_sources(sources),"claim_issues":self.validate_claims(claims),"gap_issues":self.validate_gaps(gaps),"concept_issues":self.validate_concepts(sources),"text_issues":self.audit_text(text,sources) if text else [],"principle":"Validation flags traceability and reasoning risks; it does not certify truth."}
