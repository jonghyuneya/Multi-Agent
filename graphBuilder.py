from IPython.display import Image, display

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import MessagesState
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import tools_condition, ToolNode
from tools import tools, llm_with_tools
from load_system_prompt import load_system_prompt
from class import AgentState

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

import asyncio

# System message
JSON_PATH = r"C:\Users\82107\Desktop\KUBIG\agent\searchNaver\orchestrator_system_prompt.json"
SYSTEM_PROMPT = load_system_prompt(JSON_PATH)

sys_msg = SystemMessage(content=SYSTEM_PROMPT)

# Node
async def orchestrator(AgentState):
    await llm_with_tools.ainvoke([sys_msg + AgentState])
    # 이렇게 AgentState 그대로 넣어줘도 되나?
   return AgentState
   #리턴 뭘로 해야하지?

# Graph
builder = StateGraph(AgentState)

# Define nodes: these do the work
builder.add_node("assistant", orchestrator)
builder.add_node("tools", ToolNode(tools))

# Define edges: these determine the control flow
builder.add_edge(START, "assistant")
builder.add_conditional_edges(
    "assistant",
    # If the latest message (result) from assistant is a tool call -> tools_condition routes to tools
    # If the latest message (result) from assistant is a not a tool call -> tools_condition routes to END
    tools_condition,
)
builder.add_edge("tools", "orchestrator")

memory = MemorySaver()
graph = builder.compile(interrupt_before=["assistant"], checkpointer=memory)
# 여기 컴파일 부분에서 interrupt 사용
# Show
display(Image(graph.get_graph(xray=True).draw_mermaid_png()))