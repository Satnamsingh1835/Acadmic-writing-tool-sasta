import argparse,json
from pathlib import Path
from .config import load_config
from .extractor import extract_source
from .parsing import read_source
from .synthesis import Synthesizer
from .validation import Validator
from .io import write_csv,write_json,write_markdown_matrix,write_sqlite
def main():
 p=argparse.ArgumentParser(prog="research-synthesist");sub=p.add_subparsers(dest="cmd",required=True)
 s=sub.add_parser("source");s.add_argument("file");s.add_argument("--id",required=True);s.add_argument("--title",default="");s.add_argument("-o","--output")
 for name in ("matrix","debate-map","gap-analysis","concept-map","historical-synthesis","research-questions","audit"):
  x=sub.add_parser(name);x.add_argument("files",nargs="+");x.add_argument("-o","--output",default=f"outputs/{name.replace('-','_')}.json")
  if name=="matrix":x.add_argument("--format",choices=("json","csv","md","sqlite"),default="json")
  if name=="audit":x.add_argument("--text")
 a=p.parse_args();Path("outputs").mkdir(exist_ok=True);srcs=lambda:[extract_source(read_source(f),str(f)) for f in a.files];syn=Synthesizer(load_config())
 if a.cmd=="source":
  data=extract_source(read_source(a.file),a.id,a.title).to_dict();print(json.dumps(data,ensure_ascii=False,indent=2)) if not a.output else write_json(data,a.output)
 elif a.cmd=="matrix":
  rows=syn.matrix(srcs());{"json":write_json,"csv":write_csv,"md":write_markdown_matrix,"sqlite":write_sqlite}[a.format](rows,a.output)
 elif a.cmd=="debate-map":write_json(syn.debates(srcs()),a.output)
 elif a.cmd=="gap-analysis":write_json([g.__dict__ for g in syn.gaps(srcs())],a.output)
 elif a.cmd=="concept-map":write_json(syn.concepts(srcs()),a.output)
 elif a.cmd=="historical-synthesis":write_json(syn.historical(srcs()),a.output)
 elif a.cmd=="research-questions":write_json(syn.research_questions(syn.gaps(srcs())),a.output)
 elif a.cmd=="audit":write_json(Validator().quality_report(srcs(),[],Path(a.text).read_text(encoding="utf-8") if a.text else ""),a.output)
 print(a.output if hasattr(a,"output") else "")
if __name__=="__main__":main()
