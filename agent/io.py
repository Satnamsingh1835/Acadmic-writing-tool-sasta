from pathlib import Path
import csv,json,sqlite3
def write_json(data,path):Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=str),encoding="utf-8")
def write_markdown_matrix(rows,path):
 if not rows:Path(path).write_text("# Literature Matrix\n\n_No sources._\n",encoding="utf-8");return
 keys=list(rows[0]);lines=["| "+" | ".join(keys)+" |","|"+"|".join("---" for _ in keys)+"|"];lines += ["| "+" | ".join(str(r.get(k,"")).replace("\n"," ")[:500] for k in keys)+" |" for r in rows];Path(path).write_text("\n".join(lines)+"\n",encoding="utf-8")
def write_csv(rows,path):
 if not rows:return
 with open(path,"w",newline="",encoding="utf-8") as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def write_sqlite(rows,path):
 if not rows:return
 con=sqlite3.connect(path);keys=list(rows[0]);con.execute("DROP TABLE IF EXISTS literature_matrix");con.execute("CREATE TABLE literature_matrix ("+",".join('"'+k+'" TEXT' for k in keys)+")");con.executemany("INSERT INTO literature_matrix VALUES ("+(",".join("?" for _ in keys))+")",[[json.dumps(r[k],ensure_ascii=False,default=str) if isinstance(r[k],(list,dict)) else str(r[k]) for k in keys] for r in rows]);con.commit();con.close()
