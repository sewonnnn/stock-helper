"""ISSUP: 할루시네이션 판단 체인"""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import LIGHT_MODEL
from stock_agent.prompts.hallucination_grader import HALLUCINATION_GRADER_PROMPT


class GradeHallucinations(BaseModel):
    """생성된 답변이 문서에 근거하는지 판단"""
    binary_score: bool = Field(description="True if grounded, False if hallucinated")


hallucination_grader = (
    ChatPromptTemplate.from_template(HALLUCINATION_GRADER_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL, temperature=0).with_structured_output(GradeHallucinations)
)
