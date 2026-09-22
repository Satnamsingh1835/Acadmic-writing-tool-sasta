from collections import defaultdict
from .models import Gap
class Synthesizer:
 def __init__(self,config):self.config=config
 def matrix(self,sources):
  fields=("source_id","year","literature_sections","research_question","main_argument","empirical_evidence","concepts","mechanisms","methodology","sample_case","historical_period","geography","limitations","explicit_gap","implicit_gap","relevance")
  return [{f:getattr(s,f) for f in fields}|{"evidence_level":"A" if s.evidence else "E"} for s in sources]
 def concepts(self,sources):
  d=defaultdict(list)
  for s in sources:
   for c in s.concepts:d[c].append({"source_id":s.source_id,"year":s.year,"definitions":[x for x in s.definitions if x.get("concept","").lower()==c.lower()]})
  return dict(d)
 def debates(self,sources):
  by=defaultdict(list)
  for s in sources:
   for sec in s.literature_sections:by[sec].append(s)
  out=[]
  for k,v in by.items():
   if len(v)<2:continue
   positions=[{"source_id":s.source_id,"position":s.main_argument,"evidence":s.empirical_evidence,"geography":s.geography,"period":s.historical_period} for s in v]
   text=" ".join((s.main_argument+" "+" ".join(s.limitations)) for s in v).lower(); disagreement=any(w in text for w in ("however","whereas","in contrast","challenges","disputes","differs","tension","competing"))
   out.append({"debate":k,"positions":positions,"disagreement_status":"supported" if disagreement else "not_established","warning":None if disagreement else "Multiple positions are shown for comparison; the corpus does not establish a disagreement.","unresolved_questions":self._unresolved(v)})
  return out
 def _unresolved(self,items):
  qs=[];geos={s.geography for s in items if s.geography};periods={s.historical_period for s in items if s.historical_period}
  if len(geos)>1:qs.append("How far are observed relationships context-dependent across geographies?")
  if len(periods)>1:qs.append("What changes and what persists across historical periods?")
  if any(s.limitations for s in items):qs.append("Which limitation recurs across studies, and what evidence would address it?")
  if not qs:qs.append("What evidence would discriminate between the documented accounts?")
  return qs
 def gaps(self,sources):
  out=[];by=defaultdict(list)
  for s in sources:
   for sec in s.literature_sections:by[sec].append(s)
  names=list(by)
  for i,a in enumerate(names):
   for b in names[i+1:]:
    A,B=by[a],by[b];shared=set(x for s in A for x in s.concepts)&set(x for s in B for x in s.concepts)
    if shared:out.append(Gap("RELATIONAL",f"Candidate relational gap: the {a} and {b} clusters share concepts ({', '.join(sorted(shared))}), but this corpus does not establish whether they have been adequately connected.",[s.source_id for s in A+B],"D","This is an analytical possibility requiring manual verification against the full literature.","What evidence links the two processes in the same setting?"))
  for s in sources:
   if s.explicit_gap:out.append(Gap("EMPIRICAL",f"Source {s.source_id} identifies: {s.explicit_gap}",[s.source_id],"A","The source itself identifies this limitation/gap."))
  return out
 def historical(self,sources):
  d=defaultdict(list)
  for s in sources:
   for p in s.historical_period.split(", "):
    if p:d[p].append(s.source_id)
  return {"periods":dict(d),"warning":"Period labels do not establish continuity or causal change."}
 def research_questions(self,gaps):return [g.researchable_question for g in gaps if g.researchable_question]
