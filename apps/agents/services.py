"""
Groq-backed helper utilities for agents (RAG + LLM).
"""

import json
import os
from typing import List
from django.utils import timezone


from groq import Groq
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from django.conf import settings

# === Groq LLM Client ===
client = Groq(api_key=settings.GROQ_API_KEY)


def ask_llama(system_prompt: str, user_prompt: str, temperature: float = None, max_tokens: int = None) -> str:
    temperature = temperature or settings.GROQ_TEMPERATURE
    max_tokens = max_tokens or settings.GROQ_MAX_TOKENS
    response = client.chat.completions.create(
        model=settings.GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# === Local Embeddings with FAISS ===
embedder = SentenceTransformer("all-MiniLM-L6-v2")
dimension = 384
index = faiss.IndexFlatL2(dimension)
documents: List[str] = []


def add_documents(texts: List[str]):
    embeddings = embedder.encode(texts)
    index.add(np.array(embeddings).astype("float32"))
    documents.extend(texts)


def retrieve(query: str, k: int = 3) -> str:
    if not documents:
        return ""
    query_vec = embedder.encode([query])
    D, I = index.search(np.array(query_vec).astype("float32"), k)
    return "\n".join([documents[i] for i in I[0] if i < len(documents)])


# === Combined RAG Function for Agents ===
def medical_agent(query: str):
    """
    Call Groq LLM + local RAG and return a structured dict.

    The model is instructed to respond with strict JSON so downstream agents
    (DiagnosisAgent, LabAgent) can rely on keys like:
      - differential_diagnosis
      - recommended_tests
      - reasoning_chain
      - medications / treatment_plan (for prescription prompts)
    """
    context = retrieve(query)
    system_prompt = (
        "You are a clinical AI assistant. "
        "Use the provided context to answer carefully.\n\n"
        "You MUST respond with a single valid JSON object only, no extra text, "
        "no markdown, no explanations outside the JSON.\n\n"
        "General JSON structure (fields may be empty but must exist where relevant):\n"
        "{\n"
        '  \"differential_diagnosis\": [\n'
        '    {\n'
        '      \"condition\": \"...\",\n'
        '      \"probability\": 0.0,\n'
        '      \"supporting_evidence\": [\"...\"],\n'
        '      \"ruling_out_factors\": [\"...\"]\n'
        "    }\n"
        "  ],\n"
        '  \"recommended_tests\": [\n'
        '    {\n'
        '      \"test_name\": \"...\",\n'
        '      \"test_type\": \"blood/urine/imaging/other\",\n'
        '      \"rationale\": \"...\",\n'
        '      \"priority\": \"routine/urgent/stat\"\n'
        "    }\n"
        "  ],\n"
        '  \"reasoning_chain\": [\"Step 1 ...\", \"Step 2 ...\"],\n'
        '  \"urgency_level\": \"low/medium/high/critical\",\n'
        '  \"medications\": [\n'
        '    {\n'
        '      \"name\": \"...\",\n'
        '      \"dosage\": \"...\",\n'
        '      \"frequency\": \"...\",\n'
        '      \"duration\": \"...\"\n'
        "    }\n"
        "  ],\n"
        '  \"treatment_plan\": \"...\",\n'
        '  \"follow_up\": \"...\"\n'
        "}\n"
    )

    user_prompt = f"""
Context:
{context}

Doctor Query:
{query}
"""
    raw = ask_llama(system_prompt, user_prompt)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        # Fall back to string; DiagnosisAgent will wrap this safely.
        pass
    return raw