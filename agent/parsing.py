from pathlib import Path
import re
_PAGE_RE=re.compile(r"(?m)^\[PAGE\s+(\d+)\]\s*$")
_YEAR_RE=r"(?:19|20)\d{2}[a-z]?"
def read_source(path):
 p=Path(path)
 if p.suffix.lower() in {".txt",".md",".markdown"}: return p.read_text(encoding="utf-8")
 if p.suffix.lower()==".pdf":
  try:
   from pypdf import PdfReader
  except ImportError as exc: raise RuntimeError("PDF input requires pypdf; install requirements-research.txt") from exc
  return "\n\n".join(f"[PAGE {i}]\n{page.extract_text() or ''}" for i,page in enumerate(PdfReader(str(p)).pages,1))
 raise ValueError("Supported source types: .txt, .md, .markdown, .pdf")
def pages(text):
 ms=list(_PAGE_RE.finditer(text))
 if not ms:return [(1,text)]
 return [(int(m.group(1)),text[m.end():(ms[i+1].start() if i+1<len(ms) else len(text))].strip()) for i,m in enumerate(ms)]
def chunks(text,max_chars=6000):
 out=[]
 for page,body in pages(text):
  cur=""
  for para in re.split(r"\n\s*\n+",body):
   para=para.strip()
   if not para:continue
   if cur and len(cur)+len(para)+2>max_chars:out.append({"page":page,"text":cur});cur=""
   cur=(cur+"\n\n"+para).strip()
  if cur:out.append({"page":page,"text":cur})
 return out
def sentences(text):
 return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-ZÀ-ÖØ-Þ0-9\[\"])",text.strip()) if s.strip()]
def first_sentences(text,terms,limit=5):
 return [s for s in sentences(text) if any(t.lower() in s.lower() for t in terms)][:limit]
def author_year(text):
 for pattern in (rf"(?m)^\s*([A-Z][A-Za-z .,&'’\-]+?)\s*\(({_YEAR_RE})\)",rf"\b([A-Z][A-Za-z'’\-]+(?:\s+et al\.)?)\s*\(({_YEAR_RE})\)"):
  m=re.search(pattern,text)
  if m:return m.group(1).strip(),m.group(2)
 return "",""
def page_numbers(text): return sorted({p for p,_ in pages(text)})
