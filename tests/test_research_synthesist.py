from agent.extractor import extract_source
from agent.models import SynthesisClaim
from agent.synthesis import Synthesizer
from agent.validation import Validator
from agent.config import load_config
A="[PAGE 7]\nAuthor A (2001)\n\nThis study argues that land access is mediated by caste. Evidence from interviews documents unequal access. The study focuses on post-independence India.\n"
B="[PAGE 3]\nAuthor B (2015)\n\nThis study examines commons governance and finds that access depends on village rules and authority. Evidence comes from ethnographic observation. The relationship to caste is underexplored.\n"
def test_extraction_page_provenance():
 r=extract_source(A,"A");assert r.year=="2001" and r.evidence[0]["page"]==7 and "caste" in r.concepts

def test_relational_gap_is_corpus_limited():
 a=extract_source(A,"A");b=extract_source(B,"B");g=[x for x in Synthesizer(load_config()).gaps([a,b]) if x.gap_type=="RELATIONAL"];assert g and g[0].evidence_level=="C" and "corpus" in g[0].statement

def test_validator_flags_traceability_and_pages():
 r=extract_source(A,"A");r.evidence=[];assert any(x["type"]=="MISSING_TRACEABILITY" for x in Validator().validate_sources([r]));issues=Validator().validate_claims([SynthesisClaim("x","A",[],[0])]);assert any(x["type"]=="UNSUPPORTED_CLAIM" for x in issues) and any(x["type"]=="INVALID_PAGE" for x in issues)

def test_validator_flags_citation_mismatch_and_overclaim():
 r=extract_source(A,"A");k={x["type"] for x in Validator().audit_text("[UNKNOWN p. 3] This proves the claim.",[r])};assert {"CITATION_MISMATCH","POSSIBLE_OVERCLAIM"}<=k

def test_config_is_editable():
 c=load_config();assert c["agent_name"].startswith("Research Synthesist") and "RELATIONAL" in c["gap_types"]
