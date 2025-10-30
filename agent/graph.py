from __future__ import annotations
import os
from typing import Any, Dict, List

from langgraph.graph import END, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt.tool_node import ToolNode
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from openai import AzureOpenAI

from shared.tools import (
    time_tool,
    api_info_tool,
    api_user_tool,
    get_product_data_tool,
    get_all_products_data_tool,
    get_product_kv_pairs_tool,
    tools_spec,
    recent_tool_context,
    verification_prompt_messages,
)

def make_client():
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-04-01-preview"),
        azure_endpoint=os.getenv("AZURE_OPENAI_API_BASE"),
    )

CLIENT = make_client()
MODEL = os.getenv("AZURE_OPENAI_MODEL", "gpt-4.1")

def lc_to_openai(msg):
    if isinstance(msg, SystemMessage):
        return {"role": "system", "content": msg.content}
    if isinstance(msg, HumanMessage):
        return {"role": "user", "content": msg.content}
    if isinstance(msg, ToolMessage):
        return {"role": "tool", "content": msg.content or "", "tool_call_id": getattr(msg, "tool_call_id", None)}
    if isinstance(msg, AIMessage):
        base = {"role": "assistant", "content": msg.content or ""}
        ak = (msg.additional_kwargs or {})
        if "function_call" in ak:
            base["function_call"] = ak["function_call"]
        if "tool_calls" in ak:
            base["tool_calls"] = ak["tool_calls"]
        return base
    if isinstance(msg, dict):
        return msg
    return {"role": "user", "content": str(msg)}

def needs_tool(state: dict) -> bool:
    last = state["messages"][-1]
    if isinstance(last, AIMessage):
        ak = (last.additional_kwargs or {})
        return bool(ak.get("tool_calls") or ak.get("function_call"))
    if isinstance(last, dict):
        return bool(last.get("tool_calls") or last.get("function_call"))
    return False

def _extract_context_from_history(messages):
    """Extract designations and fields from actual tool call history"""
    last_designations = []
    last_field = None
    
    for m in reversed(messages):
        if isinstance(m, AIMessage) and (m.additional_kwargs or {}).get("tool_calls"):
            tool_calls = (m.additional_kwargs or {})["tool_calls"]
            for tc in tool_calls:
                if "function" not in tc:
                    continue
                fname = tc["function"].get("name", "")
                try:
                    import json
                    args = json.loads(tc["function"].get("arguments", "{}"))
                    
                    if "product" in fname.lower() or "kv" in fname.lower():
                        if "designation" in args and args["designation"]:
                            last_designations.append(args["designation"])
                    
                    if "field" in args and args["field"]:
                        last_field = args["field"]
                except:
                    pass
            
            if last_designations:
                break  
    
    return last_designations[:3], last_field  

def _inject_ephemeral_contract(formatted_messages, state_messages):
    """Inject system prompt with context extracted from conversation history"""
    
    last_designations, last_field = _extract_context_from_history(state_messages)
    
    context_hint = ""
    if last_designations:
        context_hint += f"\nRecent designations discussed: {', '.join(last_designations)}"
    if last_field:
        context_hint += f"\nLast field queried: {last_field}"
    
    sys = (
        "You are a product information assistant. Answer STRICTLY from tool evidence.\n\n"
        "=== WORKFLOW ===\n"
        "1) To list all products: call get_all_products_data_tool(), extract 'designation' from each object\n\n"
        "2) To get product attributes: call get_product_kv_pairs_tool(designation='...')\n"
        "   This returns flattened key-value pairs like:\n"
        '   {"items":[{"designation":"6205","kv":[\n'
        '     {"path":"dimensions[0].name","value":"Outside diameter"},\n'
        '     {"path":"dimensions[0].value","value":52},\n'
        '     {"path":"dimensions[0].unit","value":"mm"},\n'
        '     {"path":"dimensions[0].symbol","value":"D"},\n'
        '     {"path":"dimensions[2].name","value":"Width"},\n'
        '     {"path":"dimensions[2].value","value":15},\n'
        '     {"path":"dimensions[2].unit","value":"mm"},\n'
        '     {"path":"dimensions[2].symbol","value":"B"}\n'
        "   ]}]}\n\n"
        "=== HOW TO READ KV PAIRS ===\n"
        "To find 'Width':\n"
        "  1. Scan for path ending in '.name' where value='Width' (found at dimensions[2].name)\n"
        "  2. Same index [2] will have .value and .unit (dimensions[2].value=15, dimensions[2].unit='mm')\n"
        "  3. Answer: '15 mm'\n\n"
        "To find by symbol (e.g., 'B' for width, 'd' for inner diameter, 'D' for outer diameter):\n"
        "  1. Scan for path ending in '.symbol' where value='B'\n"
        "  2. Use same index to get .value and .unit\n\n"
        "=== EXAMPLE QUERY ===\n"
        "User: 'width of 6205?'\n"
        "1. Call: get_product_kv_pairs_tool(designation='6205')\n"
        "2. Find: dimensions[2].symbol='B' and dimensions[2].name='Width'\n"
        "3. Read: dimensions[2].value=15, dimensions[2].unit='mm'\n"
        "4. Answer: 'The width of 6205 is 15 mm.'\n\n"
        "=== FIELD MAPPINGS ===\n"
        "- Width/B: Look for symbol='B' or name='Width'\n"
        "- Inner diameter/d: Look for symbol='d' or name='Bore diameter'\n"
        "- Outer diameter/D: Look for symbol='D' or name='Outside diameter'\n"
        "- Limiting speed: Look for symbol='nlim' or name='Limiting speed'\n"
        "- Reference speed: Look for name='Reference speed'\n\n"
        "=== FOLLOW-UPS ===\n"
        f"Recent context: {last_designations[0] if last_designations else 'none'}\n"
        "If user asks 'what about its width?' without specifying product, use recent context.\n\n"
        "=== RULES ===\n"
        "- NEVER invent values\n"
        "- ALWAYS quote exact values from KV pairs\n"
        "- Include units when present\n"
        "- If truly not found after checking all paths, say 'not found in evidence'\n"
        f"{context_hint}"
    )
    return [{"role": "system", "content": sys}] + formatted_messages

def _run_model(state, config):
    lc_messages = state["messages"]
    formatted = [lc_to_openai(m) for m in lc_messages]
    formatted = _inject_ephemeral_contract(formatted, lc_messages)

    resp = CLIENT.chat.completions.create(
        model=MODEL,
        messages=formatted,
        tools=tools_spec(),
        tool_choice="auto",
    )
    msg = resp.choices[0].message
    tcs = getattr(msg, "tool_calls", None)
    fc = getattr(msg, "function_call", None)

    if tcs:
        ai = AIMessage(
            content=msg.content or "",
            additional_kwargs={
                "tool_calls": [
                    {
                        "id": getattr(tc, "id", None),
                        "type": getattr(tc, "type", "function"),
                        "function": {
                            "name": getattr(tc.function, "name", None),
                            "arguments": getattr(tc.function, "arguments", "{}"),
                        },
                    } for tc in tcs
                ]
            },
        )
        return {"messages": [ai]}
    elif fc:
        ai = AIMessage(
            content=msg.content or "",
            additional_kwargs={
                "function_call": {
                    "name": getattr(fc, "name", None),
                    "arguments": getattr(fc, "arguments", "{}"),
                }
            },
        )
        return {"messages": [ai]}

    draft = msg.content or ""
    pairs = recent_tool_context(lc_messages, max_pairs=3)
    try:
        if draft.strip():
            v_prompt = verification_prompt_messages(draft, pairs)
            v_resp = CLIENT.chat.completions.create(
                model=MODEL, messages=v_prompt, temperature=0
            )
            verified = (v_resp.choices[0].message.content or "").strip()
            final_text = verified if verified else draft
        else:
            final_text = "I don't have enough evidence from the loaded data."
    except Exception:
        final_text = draft or "I don't have enough evidence from the loaded data."

    tools_used = []
    for m in reversed(lc_messages):
        if isinstance(m, AIMessage) and (m.additional_kwargs or {}).get("tool_calls"):
            tools_used = [
                tc["function"]["name"] for tc in (m.additional_kwargs or {})["tool_calls"]
                if "function" in tc and "name" in tc["function"]
            ]
            break
    
    tools_str = ", ".join(tools_used) if tools_used else "none"
    final_text = (final_text or "").rstrip() + f"\n\nTools used: {tools_str}"
    return {"messages": [AIMessage(content=final_text)]}

def build_graph():
    g = StateGraph(MessagesState)
    g.add_node("agent", RunnableLambda(_run_model))
    g.add_node("tools", ToolNode([
        time_tool,
        api_info_tool,
        api_user_tool,
        get_product_data_tool,
        get_all_products_data_tool,
        get_product_kv_pairs_tool,
    ]))
    g.set_entry_point("agent")
    g.add_conditional_edges("agent", lambda s: "tools" if needs_tool(s) else END, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile()

GRAPH = build_graph()