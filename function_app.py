from __future__ import annotations
import json
import re
from typing import Any, Dict, List
import azure.functions as func
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from agent.graph import GRAPH

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

SESSION_STORE: Dict[str, List[Any]] = {}

def _cors():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-Id",
    }

def _extract_metadata_from_answer(answer: str, messages: List[Any]) -> Dict[str, Any]:
    """
    POST-LLM VALIDATION: Extract confidence, grounding, hallucination from LLM response.
    This validates the QUALITY of the answer, not the safety of the input.
    """
    confidence = "Unknown"
    conf_match = re.search(r'Confidence:\s*([0-9.]+|High|Medium|Low)', answer, re.IGNORECASE)
    if conf_match:
        confidence = conf_match.group(1)
    
    if confidence.replace(".", "").isdigit():
        conf_val = float(confidence)
        if conf_val >= 0.8:
            confidence_label = "High"
        elif conf_val >= 0.5:
            confidence_label = "Medium"
        else:
            confidence_label = "Low"
    else:
        confidence_label = confidence
    
    evidence = []
    ev_match = re.search(r'Evidence:\s*([E0-9,\s]+)', answer, re.IGNORECASE)
    if ev_match:
        evidence = [e.strip() for e in ev_match.group(1).split(',') if e.strip()]
    
    has_tool_evidence = False
    tools_used = []
    
    for m in reversed(messages):
        if isinstance(m, AIMessage) and (m.additional_kwargs or {}).get("tool_calls"):
            tool_calls = (m.additional_kwargs or {})["tool_calls"]
            tools_used = [
                tc["function"]["name"] for tc in tool_calls
                if "function" in tc and "name" in tc["function"]
            ]
            has_tool_evidence = bool(tools_used)
            break
        elif isinstance(m, ToolMessage):
            has_tool_evidence = True
    
    grounded = has_tool_evidence and bool(evidence)
    
    no_evidence_phrases = [
        "don't have enough evidence",
        "not found in evidence",
        "no evidence",
        "cannot find",
        "not available in the data",
        "lack evidence"
    ]
    has_no_evidence = any(phrase in answer.lower() for phrase in no_evidence_phrases)
    
    hallucination = not grounded or has_no_evidence
    
    
    return {
        "confidence": confidence_label,
        "grounding": {
            "grounded": grounded,
            "hallucination": hallucination
        },
        "safety": {
            "malicious": False  
        },
        "tools_used": tools_used,
        "evidence": evidence
    }

def _check_malicious_input(text: str) -> tuple[bool, str]:
    """
    Check if user input contains malicious intent.
    Returns (is_malicious: bool, reason: str)
    """
    if not text:
        return False, ""
    
    lower = text.lower()
    
    malicious_patterns = [
        ("hack", "unauthorized access attempts"),
        ("password", "attempting to access credentials"),
        ("credit card", "requesting sensitive financial data"),
        ("bank", "banking credential requests"),
        ("login", "login credential requests"),
        ("bypass", "security bypass attempts"),
        ("exploit", "exploitation attempts"),
        ("ddos", "denial of service attempts"),
        ("steal", "data theft attempts"),
        ("token", "authentication token requests"),
        ("api key", "API key theft attempts"),
        ("credentials", "credential theft attempts"),
        ("drop table", "SQL injection attempts"),
        ("' or '1'='1", "SQL injection attempts"),
        ("rm -rf", "destructive system commands"),
        ("delete *", "destructive operations"),
    ]
    
    for keyword, reason in malicious_patterns:
        if keyword in lower:
            return True, reason
    
    return False, ""

@app.function_name(name="chat")
@app.route(route="chat", methods=["POST", "OPTIONS"])
def chat(req: func.HttpRequest) -> func.HttpResponse:
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors())

    try:
        body = req.get_json()
    except ValueError:
        body = {}

    user_text = (body.get("text") or "").strip()
    session_id = (body.get("session_id") or req.headers.get("x-session-id") or "default").strip() or "default"
    
    is_malicious, malicious_reason = _check_malicious_input(user_text)
    
    if is_malicious:
        refusal_message = (
            "I cannot assist with this request. "
            "I'm designed to provide product information only and cannot help with "
            "unauthorized access, hacking, or requests involving sensitive credentials."
        )
        
        payload = {
            "final_answer": refusal_message,
            "confidence": "High",
            "grounding": {
                "grounded": False,
                "hallucination": False
            },
            "safety": {
                "malicious": True,
                "reason": malicious_reason
            },
            "reasoning": f"Blocked request: {malicious_reason}",
            "decision": {
                "tool": "safety_filter",
                "designation": None,
                "field": None
            },
            "tool_call": {
                "name": ["safety_filter"],
                "found": False
            },
            "evidence": []
        }
        
        return func.HttpResponse(
            json.dumps({"ok": True, "answer": json.dumps(payload, ensure_ascii=False)}, ensure_ascii=False),
            status_code=200,
            mimetype="application/json",
            headers=_cors()
        )
    
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = []
    
    SESSION_STORE[session_id].append(HumanMessage(content=user_text))
    
    result = GRAPH.invoke({"messages": SESSION_STORE[session_id]})
    
    SESSION_STORE[session_id] = result.get("messages", [])
    
    final = SESSION_STORE[session_id][-1] if SESSION_STORE[session_id] else None
    
    if isinstance(final, AIMessage):
        content = final.content
    elif isinstance(final, str):
        content = final
    else:
        content = getattr(final, "content", "") or ""
    
    metadata = _extract_metadata_from_answer(content, SESSION_STORE[session_id])
    
    payload = {
        "final_answer": content,
        "confidence": metadata["confidence"],
        "grounding": metadata["grounding"],
        "safety": metadata["safety"],
        "reasoning": f"Used tools: {', '.join(metadata['tools_used']) if metadata['tools_used'] else 'none'}",
        "decision": {
            "tool": metadata["tools_used"][0] if metadata["tools_used"] else "no_tool",
            "designation": None,  
            "field": None
        },
        "tool_call": {
            "name": metadata["tools_used"],
            "found": metadata["grounding"]["grounded"]
        },
        "evidence": metadata["evidence"]
    }
    
    return func.HttpResponse(
        json.dumps({"ok": True, "answer": json.dumps(payload, ensure_ascii=False)}, ensure_ascii=False),
        status_code=200, 
        mimetype="application/json", 
        headers=_cors()
    )

@app.function_name(name="clear_session")
@app.route(route="clear_session", methods=["POST", "OPTIONS"])
def clear_session(req: func.HttpRequest) -> func.HttpResponse:
    """Optional endpoint to clear a session"""
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors())
    
    try:
        body = req.get_json()
    except ValueError:
        body = {}
    
    session_id = (body.get("session_id") or req.headers.get("x-session-id") or "default").strip() or "default"
    
    if session_id in SESSION_STORE:
        del SESSION_STORE[session_id]
        return func.HttpResponse(
            json.dumps({"ok": True, "message": f"Session {session_id} cleared"}),
            status_code=200, mimetype="application/json", headers=_cors()
        )
    
    return func.HttpResponse(
        json.dumps({"ok": False, "message": "Session not found"}),
        status_code=404, mimetype="application/json", headers=_cors()
    )

@app.function_name(name="debug_kv")
@app.route(route="debug_kv", methods=["POST", "OPTIONS"])
def debug_kv(req: func.HttpRequest) -> func.HttpResponse:
    """Debug endpoint to see raw KV tool output"""
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors())
    
    try:
        body = req.get_json()
    except ValueError:
        body = {}
    
    designation = body.get("designation")
    
    from shared.tools import get_product_kv_pairs_tool
    result = get_product_kv_pairs_tool.invoke({"designation": designation} if designation else {})
    
    return func.HttpResponse(
        result,
        status_code=200,
        mimetype="application/json",
        headers=_cors()
    )

@app.function_name(name="upload")
@app.route(route="upload", methods=["POST", "OPTIONS"])
def upload(req: func.HttpRequest) -> func.HttpResponse:
    """Upload product JSON files to the data directory"""
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors())
    
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )
    
    filename = body.get("filename", "").strip()
    content = body.get("content", "").strip()
    
    if not filename:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Missing filename"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )
    
    if not content:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Missing content"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )
    
    if not filename.lower().endswith(".json"):
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Only .json files allowed"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )
    
    try:
        json.loads(content)
    except json.JSONDecodeError as e:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": f"Invalid JSON content: {str(e)}"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )
    
    import os
    from pathlib import Path
    
    data_dir = os.getenv("PRODUCT_DATA_DIR")
    if not data_dir:
        data_dir = os.path.join(os.path.dirname(__file__), "data")
    
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    
    safe_filename = os.path.basename(filename)
    file_path = data_path / safe_filename
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        file_size = len(content.encode("utf-8"))
        
        return func.HttpResponse(
            json.dumps({
                "ok": True,
                "message": "File uploaded successfully",
                "saved_to": str(file_path),
                "bytes": file_size,
                "filename": safe_filename
            }),
            status_code=200,
            mimetype="application/json",
            headers=_cors()
        )
    
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": f"Failed to save file: {str(e)}"}),
            status_code=500,
            mimetype="application/json",
            headers=_cors()
        )