from .config import load_config
from .extractor import extract_source
from .parsing import read_source
from .synthesis import Synthesizer
from .validation import Validator
class ResearchSynthesist:
 def __init__(self,config_path=None):self.config=load_config(config_path);self.synth=Synthesizer(self.config);self.validator=Validator()
 def analyze_sources(self,paths):return [extract_source(read_source(p),str(p)) for p in paths]
 def run(self,paths):
  sources=self.analyze_sources(paths);return {"sources":[s.to_dict() for s in sources],"matrix":self.synth.matrix(sources),"debates":self.synth.debates(sources),"concepts":self.synth.concepts(sources),"historical":self.synth.historical(sources),"gaps":[g.__dict__ for g in self.synth.gaps(sources)],"quality":self.validator.quality_report(sources,[])}
