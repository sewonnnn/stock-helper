"""용어 답변 생성 체인"""

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from stock_agent.utils.constants import LIGHT_MODEL
from stock_agent.prompts.glossary import GLOSSARY_PROMPT

generation_chain = (
    ChatPromptTemplate.from_template(GLOSSARY_PROMPT)
    | ChatOpenAI(model=LIGHT_MODEL, temperature=0)
    | StrOutputParser()
)
