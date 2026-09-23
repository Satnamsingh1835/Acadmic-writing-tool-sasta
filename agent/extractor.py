from __future__ import annotations
import re
from pathlib import Path
from .models import SourceRecord
from .parsing import author_year,chunks,first_sentences,page_numbers
CONCEPTS=("Caste","Jati","Varna","Caste structure","Caste relations","Caste-class","Land relations","Agrarian relations","Agrarian structure","Agrarian transformation","Agrarian change","Production relations","Mode of production","Commons","Common property","Common-pool resources","Commoning","Enclosure","Social boycott","Exclusion","Dalit assertion","Resistance","Village institution","Social reproduction")
SECTIONS={"LAND AND CASTE RELATIONS IN INDIA":("caste","land","agrarian","class"),"COMMONS AND CASTE":("commons","commoning","common property","access","governance"),"CONCEPTUALISING SOCIAL BOYCOTT":("social boycott","boycott","exclusion","collective punishment"),"LAND STRUGGLES IN PUNJAB":("punjab","shamlat","panchayat","land struggle","dalit")}
GEOGRAPHIES=("Punjab","Malwa","India","Tamil Nadu","Andhra Pradesh","Odisha","Vidarbha","Uttar Pradesh","Bihar","Maharashtra","Haryana","Rajasthan")
PERIOD_TERMS={"ANCIENT":("ancient","early india"),"MEDIEVAL":("medieval","precolonial"),"COLONIAL":("colonial","british rule","raj"),"POSTCOLONIAL":("post-independence","postcolonial","after independence"),"CONTEMPORARY":("contemporary","present","recent","twenty-first century")}
def _page_for_position(text,position):
 current=1
 for m in re.finditer(r"(?m)^\[PAGE\s+(\d+)\]\s*$",text):
  if m.start()<=position: current=int(m.group(1))
  else: break
 return current
def _definitions(text,concepts):
 out=[]
 for c in concepts:
  for m in re.finditer(rf"\b{re.escape(c)}\b\s+(?:is|are|refers? to|means|defined as)\s+([^.;\n]{{20,500}})",text,re.I):
   out.append({"concept":c,"definition":m.group(0).strip(),"page":_page_for_position(text,m.start()),"evidence_level":"A"})
 return out
def extract_source(text,source_id,title="",path=None):
 author,year=author_year(text); low=text.lower()
 concepts=[c for c in CONCEPTS if c.lower() in low]
 geos=[g for g in GEOGRAPHIES if g.lower() in low]
 periods=[p for p,terms in PERIOD_TERMS.items() if any(t in low for t in terms)]
 sections=[s for s,terms in SECTIONS.items() if any(t in low for t in terms)]
 args=first_sentences(text,("argue","argues","argument","thesis","suggests","finds","shows"),4)
 ev=first_sentences(text,("evidence","data","interview","survey","ethnograph","case study","documents","finds","found"),6)
 mech=first_sentences(text,("mechanism","through which","because","mediates","produces","reproduces","enforces","excludes"),5)
 gaps=first_sentences(text,("gap","underexplored","unexplored","little is known","remains unclear","limited attention"),3)
 lim=first_sentences(text,("limitation","limit","caveat","cannot","does not","scope"),4)
 r=SourceRecord(source_id=source_id,author=author,year=year,title=title or (Path(path).name if path else ""),geography=", ".join(geos),historical_period=", ".join(periods),concepts=concepts,definitions=_definitions(text,concepts),literature_sections=sections,main_argument=" ".join(args),empirical_evidence=ev,mechanisms=mech,explicit_gap=" ".join(gaps),limitations=lim,evidence=[{"source_id":source_id,"page":c["page"],"snippet":c["text"][:1000],"evidence_level":"A"} for c in chunks(text)[:50] if c["text"].strip()],keywords=concepts,uncertain_fields=["publication","discipline","research_question","research_problem","theoretical_framework","methodology","methods","data","sample_case","actors","institutions","causal_claims","historical_claims","counterarguments","findings","contribution","implicit_gap"])
 if not page_numbers(text): r.uncertain_fields.append("page provenance is unavailable in plain text")
 return r
