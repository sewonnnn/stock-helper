"""ISREL: 문서 관련성 판단 체인"""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import LIGHT_MODEL
from stock_agent.prompts.retrieval_grader import RETRIEVAL_GRADER_PROMPT


class GradeDocuments(BaseModel):
    """검색된 문서가 질문과 관련 있는지 판단"""
    binary_score: str = Field(description='"yes" or "no"')


retrieval_grader = (
    ChatPromptTemplate.from_template(RETRIEVAL_GRADER_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL, temperature=0).with_structured_output(GradeDocuments)
)
