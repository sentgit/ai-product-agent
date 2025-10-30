from __future__ import annotations
import os, json
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime
from glob import glob

from langchain_core.tools import tool
from collections import deque
from typing import Iterable, Tuple

def get_current_time():
    return {"current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

def search_api_info(APIname=None, source=None, target=None):
    import pandas as pd
    data = {
        'APIname': ['CustomerSync', 'OrderPush', 'UserCreate'],
        'source_system': ['CRM', 'WebApp', 'MobileApp'],
        'target_system': ['SAP', 'ERP', 'AuthServer'],
        'log_info': ['Success at 10:05AM', 'Timeout at 11:45AM', 'Created user ID 123']
    }
    df = pd.DataFrame(data)
    if APIname: df = df[df['APIname'].str.contains(APIname, case=False)]
    if source: df = df[df['source_system'].str.contains(source, case=False)]
    if target: df = df[df['target_system'].str.contains(target, case=False)]
    return df.to_json(orient="records") if not df.empty else "No matching API info found."

def get_api_user_info(APIname=None):
    import pandas as pd
    data = {
        'APIname': ['CustomerSync', 'OrderPush', 'UserCreate'],
        'executed_by': ['alice@company.com', 'bob@company.com', 'carol@company.com'],
        'execution_time': ['10:05 AM', '11:45 AM', '12:30 PM']
    }
    df = pd.DataFrame(data)
    if APIname: df = df[df['APIname'].str.contains(APIname, case=False)]
    return df.to_json(orient="records") if not df.empty else "No user info found."

_PRODUCT_DATASET_PATH = os.path.abspath(os.getenv("PRODUCT_DATASET_PATH", "./data/products/sample.json"))
_PRODUCT_DATASET_DIR  = os.path.abspath(os.getenv("PRODUCT_DATASET_DIR",  "./data/products"))

def _flatten_kv(obj: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    """
    Breadth-first flatten of any JSON. Yields (json_path, primitive_value).
    """
    q = deque([(prefix, obj)])
    while q:
        path, node = q.popleft()
        if isinstance(node, dict):
            for k, v in node.items():
                p = f"{path}.{k}" if path else k
                if isinstance(v, (dict, list)):
                    q.append((p, v))
                else:
                    yield p, v
        elif isinstance(node, list):
            for i, v in enumerate(node):
                p = f"{path}[{i}]"
                if isinstance(v, (dict, list)):
                    q.append((p, v))
                else:
                    yield p, v
        else:
            yield path or "$", node

def _designation_of(obj: dict) -> str | None:
    """Extract designation/title/name from a product object"""
    for key in ("designation", "title", "name", "product_name"):
        v = obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if isinstance(obj.get("product"), dict):
        for key in ("designation", "title", "name", "product_name"):
            v = obj["product"].get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
    return None

def set_product_dataset_path(path: str):
    global _PRODUCT_DATASET_PATH
    _PRODUCT_DATASET_PATH = os.path.abspath(path)

def get_current_product_dataset_path() -> str:
    return _PRODUCT_DATASET_PATH

def set_product_dataset_dir(path: str):
    global _PRODUCT_DATASET_DIR
    _PRODUCT_DATASET_DIR = os.path.abspath(path)

def get_current_product_dataset_dir() -> str:
    return _PRODUCT_DATASET_DIR

def get_product_data(file_path: Optional[str] = None) -> str:
    """Read a single product JSON file"""
    path = os.path.abspath(file_path or _PRODUCT_DATASET_PATH)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return json.dumps(data, ensure_ascii=False)
    except FileNotFoundError:
        return json.dumps({"error": f"File not found: {path}"})
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON in {path}: {e}"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def get_all_products_data(directory_path: Optional[str] = None, pattern: str = "*.json") -> str:
    """
    Returns a JSON ARRAY of ALL product JSONs from directory.
    Tries multiple fallback locations if directory is not specified.
    """
    candidates: List[str] = []
    
    if directory_path:
        candidates.append(os.path.abspath(directory_path))
    
    if _PRODUCT_DATASET_DIR:
        candidates.append(os.path.abspath(_PRODUCT_DATASET_DIR))
    
    candidates.extend([
        os.path.abspath("./data/products"),
        os.path.abspath("./data"),
        os.path.join(os.path.dirname(__file__), "data", "products"),
        os.path.join(os.path.dirname(__file__), "data"),
        os.path.abspath("./"),
    ])
    
    tried: List[str] = []
    last_error: Optional[str] = None
    
    for dir_path in candidates:
        tried.append(dir_path)
        try:
            if not os.path.isdir(dir_path):
                continue
            
            paths: List[str] = sorted(glob(os.path.join(dir_path, pattern)))
            if not paths:
                continue
            
            items = []
            for p in paths:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        obj = json.load(f)
                        items.append(obj)
                except Exception as e:
                    items.append({"error": f"Failed to read {os.path.basename(p)}: {e}"})
            
            if items:
                return json.dumps(items, ensure_ascii=False)
                
        except Exception as e:
            last_error = str(e)
    
    error_msg = f"No JSON files found in any of: {tried}"
    if last_error:
        error_msg += f". Last error: {last_error}"
    return json.dumps({"error": error_msg})

@tool
def get_product_kv_pairs_tool(designation: str = None, directory_path: str = None, limit: int = 200) -> str:
    """
    Return flattened key-value pairs for either a specific product (by designation)
    or for ALL products if designation is omitted.
    
    This helps the agent discover what attributes are actually available in the data.
    """
    try:
        raw = get_all_products_data(directory_path)
        data = json.loads(raw)
        
        if isinstance(data, dict) and "error" in data:
            return json.dumps({"error": data["error"]})
        
        if not isinstance(data, list):
            return json.dumps({"error": "Expected array of products"})
        
        items_out = []
        any_trunc = False
        
        for prod in data:
            if not isinstance(prod, dict):
                continue
            
            d = _designation_of(prod)
            
            if designation and d:
                if d.lower().strip() != designation.lower().strip():
                    continue
            
            kvs = []
            cnt = 0
            truncated = False
            
            for p, v in _flatten_kv(prod):
                kvs.append({"path": p, "value": v})
                cnt += 1
                if cnt >= max(50, limit):
                    truncated = True
                    any_trunc = True
                    break
            
            items_out.append({
                "designation": d or "unknown",
                "kv": kvs,
                "truncated": truncated
            })
        
        return json.dumps({"items": items_out, "truncated": any_trunc}, ensure_ascii=False)
    
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool
def time_tool() -> str:
    """Return the current server time as a string."""
    return str(get_current_time())

@tool
def api_info_tool(APIname: str = None, source: str = None, target: str = None) -> str:
    """Return API metadata (APIname/source/target/log info)."""
    return search_api_info(APIname, source, target)

@tool
def api_user_tool(APIname: str = None) -> str:
    """Return who executed the given API and when."""
    return get_api_user_info(APIname)

@tool
def get_product_data_tool(file_path: str = None) -> str:
    """Return RAW product JSON from a single file."""
    return get_product_data(file_path)

@tool
def get_all_products_data_tool(directory_path: str = None, pattern: str = "*.json") -> str:
    """
    Return a JSON ARRAY of ALL product JSONs from directory.
    If no directory specified, searches common locations automatically.
    """
    return get_all_products_data(directory_path, pattern)

def tools_spec():
    """Tool specifications for Azure OpenAI function calling"""
    return [
        {
            "type": "function",
            "function": {
                "name": "time_tool",
                "description": "Returns the current server time.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "api_info_tool",
                "description": "Returns API metadata such as source/target system and log info.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "APIname": {"type": "string"},
                        "source": {"type": "string"},
                        "target": {"type": "string"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "api_user_tool",
                "description": "Returns who executed the API and when.",
                "parameters": {
                    "type": "object",
                    "properties": {"APIname": {"type": "string"}},
                    "required": ["APIname"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_product_kv_pairs_tool",
                "description": "Flatten product JSON into key-value paths for a given designation or all products. Use to discover available attributes.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "designation": {"type": "string", "description": "Product designation to query (optional, omit for all products)"},
                        "directory_path": {"type": "string", "description": "Directory path (optional)"},
                        "limit": {"type": "integer", "description": "Max KV pairs per product (default 200)"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_product_data_tool",
                "description": "Return RAW product JSON from a single file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to JSON file"}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_all_products_data_tool",
                "description": "Return a JSON ARRAY of ALL product JSONs from directory. Automatically searches common locations if no directory specified.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "directory_path": {"type": "string", "description": "Directory path (optional)"},
                        "pattern": {"type": "string", "description": "File pattern (default '*.json')"}
                    }
                }
            }
        }
    ]

from langchain_core.messages import AIMessage, ToolMessage

def recent_tool_context(messages, max_pairs: int = 3) -> List[Tuple[str, str]]:
    """Extract recent tool call evidence from message history"""
    pairs: List[Tuple[str, str]] = []
    i = len(messages) - 1
    
    while i >= 0 and len(pairs) < max_pairs:
        m = messages[i]
        if isinstance(m, AIMessage) and (m.additional_kwargs or {}).get("tool_calls"):
            tool_calls = (m.additional_kwargs or {})["tool_calls"]
            j = i + 1
            collected = []
            
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                collected.append(messages[j].content or "")
                j += 1
            
            joined = " ".join(collected).strip()
            snippet = (joined[:600] + "…") if len(joined) > 600 else joined
            tool_names = ", ".join([tc["function"]["name"] for tc in tool_calls if "function" in tc])
            
            if snippet:
                pairs.append((tool_names or "tool_call", snippet))
        i -= 1
    
    return list(reversed(pairs))

def verification_prompt_messages(draft: str, tool_pairs: List[Tuple[str, str]]):
    """Build verification prompt to check answer against evidence"""
    blocks = []
    for idx, (name, text) in enumerate(tool_pairs, 1):
        blocks.append(f"[E{idx} • {name}]\n{text}")
    
    ev = "\n\n".join(blocks) if blocks else "(no evidence available)"
    
    sys = (
        "You are a meticulous verifier. Your job:\n"
        "1) Compare the DRAFT answer with the EVIDENCE.\n"
        "2) The evidence contains flattened key-value pairs from JSON. For example:\n"
        "   {\"path\":\"dimensions[2].value\",\"value\":15} with {\"path\":\"dimensions[2].unit\",\"value\":\"mm\"}\n"
        "   means the value is 15 mm.\n"
        "3) If the draft correctly interprets these KV pairs, KEEP IT AS-IS.\n"
        "4) Only replace claims that are truly NOT supported by the evidence.\n"
        "5) For product dimensions/specs, if the KV pairs contain the data (even in array format),\n"
        "   the draft is grounded - don't reject it.\n"
        "6) Return ONLY the final verified answer first, then on new lines:\n"
        "   'Confidence: <0.00-1.00>' and 'Evidence: E1, E2, ...'.\n"
    )
    user = f"DRAFT:\n{draft}\n\nEVIDENCE:\n{ev}"
    
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]