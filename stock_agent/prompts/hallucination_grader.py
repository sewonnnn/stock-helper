# 할루시네이션 판단

HALLUCINATION_GRADER_PROMPT = """You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved facts.

Set of facts (retrieved documents):
{documents}

LLM generation:
{generation}

Give a binary score: true if the generation is grounded in / supported by the set of facts, false if it contains information not supported by the facts.
Strictly check that every claim in the generation can be traced back to the provided documents."""
