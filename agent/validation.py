from collections import Counter
import re
from .models import EVIDENCE_LEVELS
class Validator:
 def validate_sources(self,sources):
  issues=[]
  for sid,n in Counter(s.source_id for s in sources).items():
   if n>1:issues.append({"type":"DUPLICATE_SOURCE","source_id":sid,"severity":"error"})
  for s in sources:
   if not s.evidence:issues.append({"type":"MISSING_TRACEABILITY","source_id":s.source_id,"severity":"error"})
   for q in s.quotations:
    if q.get("page") is None:issues.append({"type":"QUOTE_MISSING_PAGE","source_id":s.source_id,"severity":"warning"})
  return issues
 def validate_claims(self,claims):
  issues=[]
  for c in claims:
   if c.evidence_level not in EVIDENCE_LEVELS:issues.append({"type":"INVALID_EVIDENCE_LEVEL","claim":c.claim})
   if c.evidence_level in {"A","B","C"} and not c.source_ids:issues.append({"type":"UNSUPPORTED_CLAIM","claim":c.claim})
   if any(not isinstance(p,int) or p<1 for p in c.pages):issues.append({"type":"INVALID_PAGE","claim":c.claim})
  return issues
 def audit_text(self,text,sources):
  known={s.source_id for s in sources};issues=[]
  for m in re.finditer(r"\[([A-Za-z0-9_-]+)(?:\s+p\.\s*(\d+))?\]",text):
   if m.group(1) not in known:issues.append({"type":"CITATION_MISMATCH","citation":m.group(0)})
  for m in re.finditer(r"\b(proves?|demonstrates?|always|never|all|none|causes?)\b",text,re.I):issues.append({"type":"POSSIBLE_OVERCLAIM","term":m.group(0),"position":m.start()})
  return issues
 def quality_report(self,sources,claims,text=""):return {"source_issues":self.validate_sources(sources),"claim_issues":self.validate_claims(claims),"text_issues":self.audit_text(text,sources) if text else [],"principle":"Validation flags traceability risks; it does not certify truth."}
