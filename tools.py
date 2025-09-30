from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
import asyncio
from key import NaverAPI_KEY, NaverAPI_SECRET
import requests
import json

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o")

@tool
async def naver_api(query: str) -> str:
    """Search Naver API for information based on the query."""
    try:
        url = f"https://openapi.naver.com/v1/search/news.json?query={query}&display=10&start=1"
        headers = {
            "X-Naver-Client-Id": NaverAPI_KEY,
            "X-Naver-Client-Secret": NaverAPI_SECRET
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Format the results
            results = []
            for item in data.get('items', []):
                results.append({
                    'title': item.get('title', ''),
                    'description': item.get('description', ''),
                    'link': item.get('link', ''),
                    'pubDate': item.get('pubDate', '')
                })
            return json.dumps(results, ensure_ascii=False, indent=2)
        else:
            return f"Error: {response.status_code} - {response.text}"
    except Exception as e:
        return f"Error searching Naver API: {str(e)}"

@tool
async def typo_service(user_question: str) -> str:
    """Fix typos in the user question using Naver API."""
    try:
        url = f"https://openapi.naver.com/v1/search/errata.json?query={user_question}&display=10&start=1"
        headers = {
            "X-Naver-Client-Id": NaverAPI_KEY,
            "X-Naver-Client-Secret": NaverAPI_SECRET
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            # Return corrected query if available
            if data.get('items') and len(data['items']) > 0:
                corrected = data['items'][0].get('errata', user_question)
                print(f"Typo correction: '{user_question}' -> '{corrected}'")
                return corrected
            print(f"No typos found in: '{user_question}'")
            return user_question
        else:
            print(f"Typo service API error: {response.status_code}")
            return user_question
    except Exception as e:
        print(f"Typo service error: {e}")
        return user_question

@tool
async def summarizer(content: str) -> str:
    """Summarize the provided content."""
    try:
        prompt = f"""
        You are a helpful assistant that summarizes content.
        Please provide a concise summary of the following content:
        
        {content}
        
        Summary:
        """
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content
    except Exception as e:
        return f"Error summarizing content: {str(e)}"

@tool
async def intent_classifier(user_question: str) -> str:
    """Classify the intent of the user question and extract search query."""
    try:
        prompt = f"""
        You are a helpful assistant that classifies user questions and extracts search queries.
        
        For the given question, please:
        1. Classify the intent into one of these categories:
           - Information Search: User wants to find information about a topic
           - News Search: User wants to find recent news about a topic
           - General Question: User has a general question
           - Other: Any other type of question
        
        2. Extract a concise search query (2-4 keywords) that would be good for searching news/information.
        
        Question: {user_question}
        
        Please respond in this format:
        Intent: [category]
        Query: [search keywords]
        """
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = response.content
        
        # Extract just the query part for searching
        if "Query:" in result:
            query = result.split("Query:")[-1].strip()
            print(f"Intent classification result: {result}")
            print(f"Extracted query: {query}")
            return query
        else:
            print(f"Intent classification result: {result}")
            return user_question
    except Exception as e:
        print(f"Error classifying intent: {str(e)}")
        return user_question

# Define tools list
tools = [naver_api, typo_service, summarizer, intent_classifier]

# Bind tools to LLM
llm_with_tools = llm.bind_tools(tools)