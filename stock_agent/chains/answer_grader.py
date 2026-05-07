"""ISUSE: 답변 유용성 판단 체인"""

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

from stock_agent.utils.constants import LIGHT_MODEL
from stock_agent.prompts.answer_grader import ANSWER_GRADER_PROMPT


class GradeAnswer(BaseModel):
    """답변이 질문에 유용한지 판단"""
    binary_score: str = Field(description='"yes" or "no"')


answer_grader = (
    ChatPromptTemplate.from_template(ANSWER_GRADER_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL, temperature=0).with_structured_output(GradeAnswer)
)
