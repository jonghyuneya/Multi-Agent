

from langsmith import traceable, trace
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState
from langgraph.graph import START, END, StateGraph
from langgraph.prebuilt import tools_condition, ToolNode
from tools import tools, llm_with_tools
from load_system_prompt import load_system_prompt
from classes import AgentState

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import asyncio
from datetime import datetime
import pytz

# System message
JSON_PATH = r"orchestrator_system_prompt.json"
SYSTEM_PROMPT = load_system_prompt(JSON_PATH)

def get_current_time_info():
    """Get current time information in Asia/Seoul timezone"""
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    return f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S KST')}"

# Add current time information to system prompt
time_info = get_current_time_info()
sys_msg = SystemMessage(content=SYSTEM_PROMPT + f"\n\n{time_info}")

# Node
async def orchestrator(state: AgentState):
    """Orchestrator node that controls the entire workflow step by step with clarification"""
    try:
        from tools import typo_service, intent_classifier, naver_api, summarizer, question_clarity_checker
        
        # Step 1: user_question is already saved in state.user_question
        
        # Step 1.5: Check if question needs clarification (only if not already clarified)
        if not state.clarification_confirmed and not state.needs_clarification:
            clarity_result = await question_clarity_checker.ainvoke({"user_question": state.user_question})
            
            # Parse clarity result
            if "Clear: NO" in clarity_result:
                # Extract clarification question
                if "Clarification:" in clarity_result:
                    clarification = clarity_result.split("Clarification:")[-1].strip()
                    state.needs_clarification = True
                    state.clarification_question = f"I want to make sure I understand your question correctly. {clarification}"
                    print(f"Question needs clarification: {state.clarification_question}")
                    return state  # Return early to ask for clarification
            else:
                print("Question is clear, proceeding with processing")
        
        # Step 2: Check for typos and get intent classification (only if clarified or clear)
        if not state.query and (state.clarification_confirmed or not state.needs_clarification):
            # Use clarified question if available, otherwise original
            question_to_process = state.user_clarification if state.user_clarification else state.user_question
            
            print(f"Processing question: '{question_to_process}'")
            
            # First check for typos
            corrected_question = await typo_service.ainvoke({"user_question": question_to_process})
            print(f"After typo correction: '{corrected_question}'")
            
            # Use intent classifier to get the query
            intent_result = await intent_classifier.ainvoke({"user_question": corrected_question})
            state.query = intent_result
            print(f"Extracted query: '{state.query}'")
        
        # Step 3: Use naver_api to search for data if we have query but no context
        if state.query and not state.context:
            search_result = await naver_api.ainvoke({"query": state.query})
            state.context = search_result
        
        # Step 4: Use summarizer to summarize context if we have context but no summary
        if state.context and not state.summary:
            summary_result = await summarizer.ainvoke({"content": state.context})
            state.summary = summary_result
        
        return state
            
    except Exception as e:
        print(f"Error in orchestrator: {e}")
        return state

# Graph
builder = StateGraph(AgentState)

# Define nodes: these do the work
builder.add_node("orchestrator", orchestrator)

# Define edges: simple linear flow since orchestrator handles everything
builder.add_edge(START, "orchestrator")
builder.add_edge("orchestrator", END)

memory = MemorySaver()
graph = builder.compile(checkpointer=memory)
# 여기 컴파일 부분에서 interrupt 사용
# Show