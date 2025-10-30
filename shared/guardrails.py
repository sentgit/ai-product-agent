from __future__ import annotations
from typing import Dict, Any, Tuple

def malicious_check(text: str) -> Tuple[bool, str]:
    """
    Simple check; always returns (refuse: bool, reason: str).
    """
    if not text:
        return False, ""
    lower = text.lower()
    bad_phrases = [
        "hack", "password", "credit card", "bank login",
        "bypass", "ddos", "illegal", "steal", "token"
    ]
    is_malicious = any(p in lower for p in bad_phrases)
    if is_malicious:
        return True, (
            "I'm sorry, but I can't assist with requests involving "
            "unauthorized access, hacking, or sensitive credentials."
        )
    return False, ""


def grounded_or_refuse(result: Dict[str, Any] | None, question: str) -> Dict[str, Any]:
    """
    Normalize tool result into a stable shape for the executor.
    """
    if not result or not result.get("found"):
        return {"refused": True, "answer": None}
    ans = result.get("answer")
    if isinstance(ans, dict):
        return {"refused": False, "answer": ans}
    ev = result.get("evidence")
    if isinstance(ev, dict):
        return {
            "refused": False,
            "answer": {
                "name": ev.get("name"),
                "value": ev.get("value"),
                "unit": ev.get("unit"),
                "symbol": ev.get("symbol"),
            },
        }
    return {"refused": False, "answer": {"name": result.get("field"), "value": result.get("value"), "unit": None, "symbol": None}}


def reasoning_summary(action: str, rationale: str) -> str:
    return f"decision={action}; rationale={rationale}"


def build_payload(
    final_answer: str,
    decision: Dict[str, Any],
    question: str,
    tool_result: Dict[str, Any] | None,
    malicious: bool,
    rationale: str,
) -> Dict[str, Any]:
    grounded = bool(tool_result) and bool(tool_result.get("found"))
    payload = {
        "final_answer": final_answer,
        "decision": decision,
        "reasoning": rationale,
        "safety": {"malicious": malicious},
        "grounding": {"grounded": grounded, "hallucination": not grounded},
        "confidence": "High" if grounded else "Low",
        "tool_call": {
            "name": decision.get("tool"),
            "args": {"designation": decision.get("designation"), "field": decision.get("field")},
            "found": tool_result.get("found") if tool_result else None,
        },
        "evidence": tool_result.get("evidence") if tool_result else None,
        "question": question,
    }
    return payload
