import json
from pathlib import Path

def load_system_prompt(json_path: str) -> str:
    p = Path(json_path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if "system_prompt" not in data:
        raise KeyError("JSON에 'system_prompt' 키가 없습니다.")
    return data["system_prompt"]

