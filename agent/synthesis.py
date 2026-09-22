from __future__ import annotations
from collections import defaultdict
from .models import Gap, SynthesisClaim
class Synthesizer:
 def __init__(self,config): self.config=config
 def matrix(self,sources):
  fields=("source_id","author","year","title","publication","discipline","literature_sections","research_question","research_problem","main_argument","secondary_arguments","empirical_evidence","concepts","mechanisms","methodology","methods","data","sample_case","historical_period","geography","actors","institutions","causal_claims","historical_claims","counterarguments","limitations","findings","contribution","explicit_gap","implicit_gap","relevance")
  return [{f:getattr(s,f) for f in fields}|{"evidence_level":"A" if s.evidence else "E","traceability_pages":sorted({e["page"] for e in s.evidence if isinstance(e.get("page"),int)})} for s in sources]
 def concepts(self,sources):
  d=defaultdict(list)
  for s in sources:
   for c in s.concepts:
    d[c].append({"source_id":s.source_id,"author":s.author,"year":s.year,"definitions":[x for x in s.definitions if x.get("concept","").lower()==c.lower()]})
  return dict(d)
 def debates(self,sources):
  by=defaultdict(list)
  for s in sources:
   for sec in s.literature_sections: by[sec].append(s)
  out=[]
  for debate,items in by.items():
   if len(items)<2: continue
   positions=[{"source_id":s.source_id,"author":s.author,"position":s.main_argument,"evidence":s.empirical_evidence,"geography":s.geography,"period":s.historical_period} for s in items]
   evidence_text=" ".join((s.main_argument+" "+" ".join(s.counterarguments)) for s in items).lower()
   disagreement=any(w in evidence_text for w in ("however","whereas","in contrast","challenges","disputes","differs","tension","competing"))
   out.append({"debate":debate,"positions":positions,"disagreement_status":"supported" if disagreement else "not_established","warning":None if disagreement else "Multiple positions are shown for comparison; the corpus does not establish disagreement.","unresolved_questions":self._unresolved(items)})
  return out
 def _unresolved(self,items):
  qs=[]; geos={s.geography for s in items if s.geography}; periods={s.historical_period for s in items if s.historical_period}
  if len(geos)>1: qs.append("How far are observed relationships context-dependent across geographies?")
  if len(periods)>1: qs.append("What changes and what persists across the documented historical periods?")
  if any(s.limitations for s in items): qs.append("Which limitation recurs across studies, and what evidence would address it?")
  if not qs: qs.append("What evidence would discriminate between the documented accounts?")
  return qs
 def gaps(self,sources):
  out=[]; by=defaultdict(list)
  for s in sources:
   for sec in s.literature_sections: by[sec].append(s)
  names=list(by)
  for i,a in enumerate(names):
   for b in names[i+1:]:
    A,B=by[a],by[b]; shared={x for s in A for x in s.concepts}&{x for s in B for x in s.concepts}
    if shared:
     out.append(Gap("RELATIONAL",f"Candidate relational gap: {a} and {b} share concepts ({', '.join(sorted(shared))}), but this corpus does not establish whether the literatures adequately connect them.",[s.source_id for s in A+B],"D","Analytical possibility only; verify through broader literature search.","What evidence, if any, connects these processes in the same setting?"))
  for s in sources:
   if s.explicit_gap: out.append(Gap("EMPIRICAL",f"Source {s.source_id} explicitly identifies: {s.explicit_gap}",[s.source_id],"A","The source itself identifies the issue."))
  return out
 def historical(self,sources):
  d=defaultdict(list)
  for s in sources:
   for p in filter(None,map(str.strip,s.historical_period.split(","))): d[p].append(s.source_id)
  return {"periods":dict(d),"caution":"Presence of a period label is not evidence of continuity, rupture, or causal change."}
 def research_questions(self,gaps): return [g.researchable_question for g in gaps if g.researchable_question]
 def connected_outline(self,sources):
  claims=[]
  for s in sources:
   if s.main_argument:
    claims.append(SynthesisClaim(f"{s.author or s.source_id} argues: {s.main_argument}","A",[s.source_id],sorted({e["page"] for e in s.evidence if isinstance(e.get("page"),int)}),[e["snippet"] for e in s.evidence[:2]],"medium"))
  return claims
