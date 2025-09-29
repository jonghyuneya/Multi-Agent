from langchain_core import messages
from langgraph.graph.message import Messages
from pydantic import BaseModel, field_validator
from langgraph.graph import MessagesState, add_messages

class AgentState(BaseModel):
    summary: str
    context: Field(description="information obtained from NaverAPI")
    query: Field(description="subject to research")
    user_question: str # query 