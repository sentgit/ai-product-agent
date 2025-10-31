from __future__ import annotations
import re
from typing import Dict, List, Tuple, Any
from datetime import datetime

class ComprehensiveGuardrails:
    
    @staticmethod
    def check_input_safety(text: str) -> Dict[str, Any]:
        violations = []
        severity = "none"
        
        if not text or not text.strip():
            return {"safe": True, "violations": [], "severity": "none", "reason": ""}
        
        lower = text.lower()
        
        critical_patterns = [
            ("hack", "Hacking attempt"),
            ("exploit", "Exploitation attempt"),
            ("bypass", "Security bypass"),
            ("sql injection", "SQL injection"),
            ("drop table", "Database manipulation"),
            ("rm -rf", "Destructive command"),
            ("exec(", "Code execution"),
            ("eval(", "Code evaluation"),
            ("<script", "XSS attempt"),
        ]
        
        high_risk_patterns = [
            ("password", "Credential request"),
            ("credit card", "Financial data request"),
            ("bank account", "Banking info request"),
            ("social security", "PII request"),
            ("api key", "API key request"),
            ("access token", "Token request"),
            ("private key", "Cryptographic key request"),
        ]
        
        medium_risk_patterns = [
            ("login", "Authentication query"),
            ("admin", "Privilege escalation"),
            ("root", "Root access"),
            ("sudo", "Elevated privileges"),
        ]
        
        pii_patterns = [
            (r'\b\d{3}-\d{2}-\d{4}\b', "SSN pattern"),
            (r'\b\d{16}\b', "Credit card pattern"),
            (r'\b\d{3}\.\d{3}\.\d{3}\.\d{3}\b', "IP address"),
        ]
        
        for pattern, desc in critical_patterns:
            if pattern in lower:
                violations.append(desc)
                severity = "critical"
        
        if severity != "critical":
            for pattern, desc in high_risk_patterns:
                if pattern in lower:
                    violations.append(desc)
                    severity = "high"
        
        if severity not in ["critical", "high"]:
            for pattern, desc in medium_risk_patterns:
                if pattern in lower:
                    violations.append(desc)
                    severity = "medium"
        
        for pattern, desc in pii_patterns:
            if re.search(pattern, text):
                violations.append(desc)
                if severity == "none":
                    severity = "medium"
        
        jailbreak_patterns = [
            "ignore previous instructions",
            "disregard all",
            "you are now",
            "new role",
            "forget everything",
            "act as if",
            "pretend you are",
            "bypass restrictions"
        ]
        
        for pattern in jailbreak_patterns:
            if pattern in lower:
                violations.append("Jailbreak attempt")
                severity = "critical"
                break
        
        excessive_length = len(text) > 5000
        if excessive_length:
            violations.append("Excessive input length")
            if severity == "none":
                severity = "low"
        
        repeated_chars = re.search(r'(.)\1{50,}', text)
        if repeated_chars:
            violations.append("Pattern flooding")
            if severity == "none":
                severity = "low"
        
        safe = severity in ["none", "low"]
        reason = "; ".join(violations) if violations else ""
        
        return {
            "safe": safe,
            "violations": violations,
            "severity": severity,
            "reason": reason
        }
    
    @staticmethod
    def check_output_safety(answer: str, original_query: str) -> Dict[str, Any]:
        issues = []
        filtered = answer
        
        pii_patterns = {
            r'\b\d{3}-\d{2}-\d{4}\b': '[SSN-REDACTED]',
            r'\b\d{16}\b': '[CARD-REDACTED]',
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b': '[EMAIL-REDACTED]',
            r'\b\d{3}-\d{3}-\d{4}\b': '[PHONE-REDACTED]',
        }
        
        for pattern, replacement in pii_patterns.items():
            if re.search(pattern, filtered):
                issues.append(f"PII detected: {replacement}")
                filtered = re.sub(pattern, replacement, filtered)
        
        sensitive_keywords = [
            'password', 'api_key', 'secret', 'token', 'private_key',
            'access_key', 'credentials'
        ]
        
        for keyword in sensitive_keywords:
            if keyword in answer.lower() and keyword not in original_query.lower():
                issues.append(f"Exposed sensitive term: {keyword}")
        
        code_execution_patterns = [
            r'exec\s*\(',
            r'eval\s*\(',
            r'os\.system\s*\(',
            r'subprocess\.',
            r'__import__\s*\(',
        ]
        
        for pattern in code_execution_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                issues.append(f"Code execution pattern detected")
                filtered = re.sub(pattern, '[CODE-REMOVED]', filtered, flags=re.IGNORECASE)
        
        sql_patterns = [
            r'DROP\s+TABLE',
            r'DELETE\s+FROM',
            r'UPDATE\s+\w+\s+SET',
            r'INSERT\s+INTO',
        ]
        
        for pattern in sql_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                issues.append(f"SQL command detected")
                filtered = re.sub(pattern, '[SQL-REMOVED]', filtered, flags=re.IGNORECASE)
        
        disallowed_urls = [
            'http://localhost',
            '127.0.0.1',
            '192.168.',
            'file://',
        ]
        
        for url in disallowed_urls:
            if url in answer.lower():
                issues.append(f"Internal URL exposed: {url}")
                filtered = filtered.replace(url, '[URL-REDACTED]')
        
        safe = len(issues) == 0
        
        return {
            "safe": safe,
            "issues": issues,
            "filtered_answer": filtered
        }
    
    @staticmethod
    def check_context_appropriateness(query: str, answer: str, context: str = "product_info") -> Dict[str, Any]:
        lower_query = query.lower()
        lower_answer = answer.lower()
        
        off_topic_keywords = {
            "medical": ["diagnosis", "treatment", "medication", "disease", "symptom", "doctor"],
            "legal": ["lawsuit", "legal advice", "attorney", "court", "sue"],
            "financial": ["investment advice", "stock tip", "financial planning", "trading"],
            "political": ["election", "vote for", "political party", "candidate"],
            "personal": ["relationship advice", "therapy", "counseling"],
        }
        
        for category, keywords in off_topic_keywords.items():
            if any(kw in lower_query for kw in keywords):
                return {
                    "appropriate": False,
                    "reason": f"Off-topic: {category} query",
                    "suggested_response": f"I'm designed to provide product information only. I cannot assist with {category} questions."
                }
        
        product_keywords = ["bearing", "product", "designation", "dimension", "speed", "diameter", "width"]
        has_product_context = any(kw in lower_answer for kw in product_keywords)
        
        if len(answer) > 100 and not has_product_context and context == "product_info":
            return {
                "appropriate": False,
                "reason": "Response lacks product context",
                "suggested_response": "I don't have information about that. I can help with product specifications, dimensions, and technical details."
            }
        
        return {
            "appropriate": True,
            "reason": "",
            "suggested_response": ""
        }
    
    @staticmethod
    def rate_limit_check(session_id: str, max_requests: int = 100, window_minutes: int = 60) -> Dict[str, Any]:
        return {
            "allowed": True,
            "remaining": max_requests,
            "reset_time": datetime.now().isoformat()
        }
    
    @staticmethod
    def validate_grounding(answer: str, evidence: List[str]) -> Dict[str, Any]:
        if not evidence:
            return {
                "grounded": False,
                "confidence": 0.0,
                "unsupported_claims": ["No evidence provided"]
            }
        
        answer_lower = answer.lower()
        
        hallucination_phrases = [
            "i think", "probably", "might be", "could be", "possibly",
            "i believe", "it seems", "perhaps", "maybe"
        ]
        
        uncertainty_count = sum(1 for phrase in hallucination_phrases if phrase in answer_lower)
        
        no_evidence_phrases = [
            "don't have enough evidence",
            "not found in evidence",
            "no evidence",
            "cannot find",
            "not available"
        ]
        
        explicitly_ungrounded = any(phrase in answer_lower for phrase in no_evidence_phrases)
        
        if explicitly_ungrounded:
            return {
                "grounded": False,
                "confidence": 0.0,
                "unsupported_claims": ["Explicit lack of evidence stated"]
            }
        
        has_citations = bool(re.search(r'\bE\d+\b', answer))
        has_specific_values = bool(re.search(r'\d+\s*(mm|cm|m|r/min|kN|kg)', answer))
        
        confidence = 0.0
        if has_citations:
            confidence += 0.4
        if has_specific_values:
            confidence += 0.3
        if uncertainty_count == 0:
            confidence += 0.3
        
        grounded = confidence >= 0.7
        
        unsupported = []
        if uncertainty_count > 2:
            unsupported.append(f"High uncertainty ({uncertainty_count} hedging phrases)")
        if not has_citations:
            unsupported.append("No evidence citations")
        if not has_specific_values:
            unsupported.append("No specific measurements")
        
        return {
            "grounded": grounded,
            "confidence": confidence,
            "unsupported_claims": unsupported
        }


def apply_all_guardrails(query: str, answer: str, evidence: List[str], session_id: str) -> Dict[str, Any]:
    guardrails = ComprehensiveGuardrails()
    
    input_check = guardrails.check_input_safety(query)
    if not input_check["safe"]:
        return {
            "allowed": False,
            "stage": "input",
            "violations": input_check["violations"],
            "severity": input_check["severity"],
            "filtered_answer": "I cannot process this request due to safety concerns.",
            "metadata": {
                "input_safe": False,
                "output_safe": None,
                "grounded": None,
                "appropriate": None
            }
        }
    
    output_check = guardrails.check_output_safety(answer, query)
    
    grounding = guardrails.validate_grounding(answer, evidence)
    
    appropriateness = guardrails.check_context_appropriateness(query, answer)
    
    rate_limit = guardrails.rate_limit_check(session_id)
    
    final_answer = output_check["filtered_answer"] if not output_check["safe"] else answer
    
    if not appropriateness["appropriate"]:
        final_answer = appropriateness["suggested_response"]
    
    return {
        "allowed": rate_limit["allowed"] and input_check["safe"],
        "stage": "complete",
        "filtered_answer": final_answer,
        "metadata": {
            "input_safe": input_check["safe"],
            "input_severity": input_check["severity"],
            "output_safe": output_check["safe"],
            "output_issues": output_check["issues"],
            "grounded": grounding["grounded"],
            "grounding_confidence": grounding["confidence"],
            "appropriate": appropriateness["appropriate"],
            "rate_limit_remaining": rate_limit["remaining"]
        }
    }