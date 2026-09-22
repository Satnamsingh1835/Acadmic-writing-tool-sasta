from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
EVIDENCE_LEVELS={"A":"DIRECT EVIDENCE","B":"STRONG INTERPRETATION","C":"CROSS-SOURCE SYNTHESIS","D":"ANALYTICAL POSSIBILITY","E":"SPECULATION"}
GAP_TYPES=("EMPIRICAL","CONCEPTUAL","THEORETICAL","METHODOLOGICAL","GEOGRAPHICAL","HISTORICAL","INSTITUTIONAL","RELATIONAL","PROCESS","SCALE")
@dataclass
class SourceRecord:
 source_id:str; author:str=""; year:str=""; title:str=""; publication:str=""; discipline:str=""; geography:str=""; historical_period:str=""; research_question:str=""; research_problem:str=""; main_argument:str=""; secondary_arguments:list[str]=field(default_factory=list); concepts:list[str]=field(default_factory=list); definitions:list[dict[str,Any]]=field(default_factory=list); theoretical_framework:list[str]=field(default_factory=list); methodology:str=""; methods:list[str]=field(default_factory=list); data:str=""; sample_case:str=""; empirical_evidence:list[str]=field(default_factory=list); mechanisms:list[str]=field(default_factory=list); actors:list[str]=field(default_factory=list); institutions:list[str]=field(default_factory=list); causal_claims:list[str]=field(default_factory=list); historical_claims:list[str]=field(default_factory=list); counterarguments:list[str]=field(default_factory=list); limitations:list[str]=field(default_factory=list); findings:list[str]=field(default_factory=list); contribution:str=""; explicit_gap:str=""; implicit_gap:str=""; quotations:list[dict[str,Any]]=field(default_factory=list); keywords:list[str]=field(default_factory=list); literature_sections:list[str]=field(default_factory=list); relevance:str=""; evidence:list[dict[str,Any]]=field(default_factory=list); uncertain_fields:list[str]=field(default_factory=list)
 def to_dict(self): return asdict(self)
@dataclass
class SynthesisClaim:
 claim:str; evidence_level:str; source_ids:list[str]; pages:list[int]=field(default_factory=list); snippets:list[str]=field(default_factory=list); confidence:str="medium"; status:str="supported"; notes:str=""
@dataclass
class Gap:
 gap_type:str; statement:str; source_ids:list[str]; evidence_level:str="C"; why_it_matters:str=""; researchable_question:str=""
@dataclass
class DecisionRequired:
 question:str; evidence:list[str]; possible_interpretations:list[str]; why_it_matters:str
