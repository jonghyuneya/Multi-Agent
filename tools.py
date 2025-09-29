from langchain_openai import ChatOpenAI
import asyncio
from key import NaverAPI_KEY, NaverAPI_SECRET
import requests

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


async def NaverAPI(AgentState):
    """Search Naver API for information."""
    url = f"https://openapi.naver.com/v1/search/news.json?query={AgentState['query']}&display=10&start=1"
    headers = {
        "X-Naver-Client-Id": NaverAPI_KEY,
        "X-Naver-Client-Secret": NaverAPI_SECRET
    }
    response = requests.get(url, headers=headers)
    return AgentState[f"context{response.json()}"]

# This will be a tool
async def TypoService(AgentState):
    """Fix typos in the query."""
    url = f"https://openapi.naver.com/v1/search/errata.json?query={AgentState['user_question']}&display=10&start=1"
    headers = {
        "X-Naver-Client-Id": NaverAPI_KEY,
        "X-Naver-Client-Secret": NaverAPI_SECRET
    }
    response = requests.get(url, headers=headers)
    return AgentState["query"]

async def Summarizer(AgentState):
    """Summarize the content."""
    brief_query = llm.invoke(AgentState["user_question"],
    prompt="""
    You are a helpful assistant that summarizes the content of the query.
    You will be given a query and you need to summarize the content of the query.
    You need to return the summary of the query.
    """)
    return AgentState["summary"]

async def intent_classifier(AgentState):
    """Classify the intent of the query."""
    brief_query = llm.invoke(AgentState["user_question"],
    prompt="""
    You are a helpful assistant that classifies the intent of the query.
    You will be given a query and you need to classify the intent of the query.
    You need to return the intent of the query.
    """)
    return AgentState[f"query={brief_query}"]


tools = [TypoService, NaverAPI, Summarizer, intent_classifier]
llm = ChatOpenAI(model="gpt-4o")
llm_with_tools = llm.bind_tools(tools)