from langchain_openai import ChatOpenAI
import asyncio

async def NaverAPI(AgentState):
    """Multiply a and b.

    Args:
        a: first int
        b: second int
    """
    return AgentState["context"]

# This will be a tool
async def TypoService(AgentState):
    """Adds a and b.

    Args:
        a: first int
        b: second int
    """
    return AgentState["query"]

async def Summarizer(AgentState):
    
    return AgentState["summary"]

async def intent_classifier(AgentState):
    
    return AgentState["query"]


tools = [TypoService, NaverAPI, Summarizer, intent_classifier]
llm = ChatOpenAI(model="gpt-4o")
llm_with_tools = llm.bind_tools(tools)