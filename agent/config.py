from pathlib import Path
import json
DEFAULT_PATH=Path(__file__).resolve().parent.parent/"config"/"research_synthesist.json"
def load_config(path=None): return json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
