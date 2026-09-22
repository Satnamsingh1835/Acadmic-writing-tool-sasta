from agent.extractor import extract_source
from agent.models import SynthesisClaim, Gap
from agent.synthesis import Synthesizer
from agent.validation import Validator
from agent.config import load_config

def test_matrix_contains_core_traceability_fields():
 s=extract_source("[PAGE 4]\nScholar (2012) argues that caste and land relations interact. Evidence from interviews supports the claim.","S1")
 row=Synthesizer(load_config()).matrix([s])[0]
 for field in ("source_id","author","year","main_argument","empirical_evidence","concepts","mechanisms","methodology","geography","limitations","relevance"):
  assert field in row

def test_direct_claim_requires_snippet():
 c=SynthesisClaim("supported","A",["S1"])
 assert any(x["type"]=="DIRECT_EVIDENCE_WITHOUT_SNIPPET" for x in Validator().validate_claims([c]))

def test_relational_gap_requires_d_level():
 g=Gap("RELATIONAL","possible linkage",["S1","S2"],"C")
 assert any(x["type"]=="RELATIONAL_GAP_REQUIRES_VERIFICATION" for x in Validator().validate_gaps([g]))

def test_concept_variation_is_flagged():
 a=extract_source("Caste is a system of ranked relations between groups. Caste shapes land access.","A")
 b=extract_source("Caste is a category used in administrative classification. Caste shapes land access.","B")
 assert any(x["type"]=="CONCEPTUAL_VARIATION" for x in Validator().validate_concepts([a,b]))
