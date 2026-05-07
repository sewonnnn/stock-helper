# 문서 관련성 판단

RETRIEVAL_GRADER_PROMPT = """You are a grader assessing the relevance of a retrieved document to a user question.

Retrieved document:
{document}

User question:
{question}

If the document contains keywords or semantic meaning related to the question, grade it as relevant.
Give a binary score: "yes" if relevant, "no" if not relevant."""
