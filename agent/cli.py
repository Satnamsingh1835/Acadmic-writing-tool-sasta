import argparse,json
from pathlib import Path
from .config import load_config
from .extractor import extract_source
from .parsing import read_source
from .synthesis import Synthesizer
from .validation import Validator
from .pipeline import ResearchSynthesist
from .io import write_csv,write_json,write_markdown_matrix,write_sqlite
from argument_diagnostics import ArgumentDiagnostics
from advanced_humanize import AdvancedHumanizer

def _sources(files):
 return [extract_source(read_source(f),str(f),path=f) for f in files]

def main():
 p=argparse.ArgumentParser(prog="research-synthesist")
 sub=p.add_subparsers(dest="cmd",required=True)
 s=sub.add_parser("source"); s.add_argument("file"); s.add_argument("--id",required=True); s.add_argument("--title",default=""); s.add_argument("-o","--output")
 for name in ("matrix","debate-map","gap-analysis","concept-map","historical-synthesis","research-questions","audit","synthesize","paragraph-audit","citation-audit","human-edit"):
  x=sub.add_parser(name); x.add_argument("files",nargs="+"); x.add_argument("-o","--output",default=f"outputs/{name.replace('-','_')}.json")
  if name=="matrix": x.add_argument("--format",choices=("json","csv","md","sqlite"),default="json")
  if name in {"audit","citation-audit"}: x.add_argument("--text",required=True)
  if name=="paragraph-audit": x.add_argument("--paragraph",required=True)
  if name=="human-edit": x.add_argument("--profile",choices=("conservative","standard","polish"),default="standard")
 a=p.parse_args(); Path("outputs").mkdir(exist_ok=True)
 syn=Synthesizer(load_config()); sources=_sources(a.files)
 if a.cmd=="source":
  data=extract_source(read_source(a.file),a.id,a.title,path=a.file).to_dict()
  if a.output: write_json(data,a.output)
  else: print(json.dumps(data,ensure_ascii=False,indent=2))
 elif a.cmd=="matrix":
  rows=syn.matrix(sources); {"json":write_json,"csv":write_csv,"md":write_markdown_matrix,"sqlite":write_sqlite}[a.format](rows,a.output)
 elif a.cmd=="debate-map": write_json(syn.debates(sources),a.output)
 elif a.cmd=="concept-map": write_json(syn.concepts(sources),a.output)
 elif a.cmd=="historical-synthesis": write_json(syn.historical(sources),a.output)
 elif a.cmd=="gap-analysis": write_json([g.__dict__ for g in syn.gaps(sources)],a.output)
 elif a.cmd=="research-questions": write_json(syn.research_questions(syn.gaps(sources)),a.output)
 elif a.cmd=="audit": write_json(Validator().quality_report(sources,[],syn.gaps(sources),Path(a.text).read_text(encoding="utf-8")),a.output)
 elif a.cmd=="citation-audit": write_json(Validator().quality_report(sources,[],[],Path(a.text).read_text(encoding="utf-8")),a.output)
 elif a.cmd=="paragraph-audit": write_json(ArgumentDiagnostics().analyse(a.paragraph),a.output)
 elif a.cmd=="human-edit":
  text=Path(a.files[0]).read_text(encoding="utf-8"); Path(a.output).write_text(AdvancedHumanizer().humanize_literature_review(text,a.profile),encoding="utf-8")
 elif a.cmd=="synthesize": write_json(ResearchSynthesist().model_synthesis(a.files),a.output)
 print(a.output)

if __name__=="__main__": main()
