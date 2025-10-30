from __future__ import annotations
import json, os, glob
from typing import Dict, Any, List, Optional

_DEFAULT_DIR = os.path.join(os.path.dirname(__file__), "data")
_ENV_DIR = os.getenv("PRODUCT_DATA_DIR")

class ProductIndex:
    def __init__(self):
        self._by_key: Dict[str, Dict[str, Any]] = {}
    def load(self, data_dir: Optional[str] = None) -> int:
        self._by_key.clear()
        dirs: List[str] = []
        if data_dir:
            dirs.extend(str(data_dir).split(os.pathsep))
        else:
            if _ENV_DIR: dirs.append(_ENV_DIR)
            dirs.append(_DEFAULT_DIR)
        count=0
        for d in dirs:
            if not d: continue
            for p in glob.glob(os.path.join(d, "**", "*.json"), recursive=True):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        obj = json.load(f)
                    key = str(obj.get("designation") or obj.get("title") or os.path.basename(p)).strip().lower()
                    self._by_key[key] = obj
                    count += 1
                except Exception:
                    pass
        return count
    def get(self, designation: str) -> Optional[Dict[str, Any]]:
        if not designation: return None
        return self._by_key.get(str(designation).strip().lower())

INDEX = ProductIndex()
INDEX.load()
