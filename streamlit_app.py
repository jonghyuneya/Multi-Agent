import streamlit as st
import asyncio
from datetime import datetime
import pytz
from classes import AgentState
from graphBuilder import graph

# Set page config
st.set_page_config(
    page_title="Orchestrator Chat",
    page_icon="🤖",
    layout="wide"
)

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "graph_state" not in st.session_state:
    st.session_state.graph_state = None

def get_current_time_info():
    """Get current time information in Asia/Seoul timezone"""
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    return f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S KST')}"

async def process_user_question(user_question: str):
    """Process user question through the orchestrator workflow"""
    try:
        # Create initial AgentState
        agent_state = AgentState(
            summary="",
            context="",
            query="",
            user_question=user_question
        )
        
        # Process through the graph
        config = {"configurable": {"thread_id": "user_session"}}
        
        # Run the graph with proper state format
        result = await graph.ainvoke(
            agent_state,
            config=config
        )
        
        return result
    except Exception as e:
        st.error(f"Error processing question: {str(e)}")
        return None

def main():
    st.title("🤖 Orchestrator Chat System")
    st.markdown("Ask questions and get AI-powered responses with tool integration!")
    
    # Display current time
    current_time = get_current_time_info()
    st.sidebar.markdown(f"**{current_time}**")
    
    # Chat interface
    st.markdown("### Chat")
    
    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("What would you like to know?"):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Process the question
        with st.chat_message("assistant"):
            with st.spinner("Processing your question..."):
                try:
                    # Run async function
                    result = asyncio.run(process_user_question(prompt))
                    
                    if result:
                        # Extract response from result - show workflow steps
                        response = ""
                        
                        # Check if result is a dict (from graph output)
                        if isinstance(result, dict):
                            if result.get('summary'):
                                response = f"**🤖 Final Summary:**\n\n{result['summary']}\n\n"
                                if result.get('query'):
                                    response += f"**🔍 Search Query Used:** {result['query']}\n\n"
                                if result.get('context'):
                                    response += f"**📰 Information Sources:**\n{result['context'][:500]}..."
                            elif result.get('context'):
                                response = f"**📰 Information Found:**\n{result['context']}"
                            else:
                                response = "I've processed your question, but couldn't generate a response. Please try again."
                        # Check if result is an AgentState object
                        elif hasattr(result, 'summary') and result.summary:
                            response = f"**🤖 Final Summary:**\n\n{result.summary}\n\n"
                            if hasattr(result, 'query') and result.query:
                                response += f"**🔍 Search Query Used:** {result.query}\n\n"
                            if hasattr(result, 'context') and result.context:
                                response += f"**📰 Information Sources:**\n{result.context[:500]}..."
                        elif hasattr(result, 'context') and result.context:
                            response = f"**📰 Information Found:**\n{result.context}"
                        elif hasattr(result, 'user_question') and result.user_question:
                            response = f"Processed: {result.user_question}"
                        else:
                            response = "I've processed your question, but couldn't generate a response. Please try again."
                        
                        st.markdown(response)
                        
                        # Add assistant response to chat history
                        st.session_state.messages.append({"role": "assistant", "content": response})
                    else:
                        error_msg = "Sorry, I encountered an error processing your question. Please try again."
                        st.error(error_msg)
                        st.session_state.messages.append({"role": "assistant", "content": error_msg})
                        
                except Exception as e:
                    error_msg = f"Error: {str(e)}"
                    st.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})
    
    # Sidebar information
    st.sidebar.markdown("### System Information")
    st.sidebar.markdown("**Available Tools:**")
    st.sidebar.markdown("- TypoService")
    st.sidebar.markdown("- IntentClassifier") 
    st.sidebar.markdown("- NaverAPI")
    st.sidebar.markdown("- Summarizer")
    
    st.sidebar.markdown("### Workflow")
    st.sidebar.markdown("""
    **The orchestrator follows this exact workflow:**
    
    1. **📝 User Input** → Save in user_question
    
    2. **🔍 Typo Check** → Check for typos using typo service
    
    3. **🎯 Intent Classification** → Extract search query from intent
    
    4. **🔎 Naver API Search** → Search for data using the query
    
    5. **📰 Get Context** → Store search results as context
    
    6. **📝 Summarize** → Summarize context for final response
    
    7. **🤖 Deliver Response** → Show summary with sources
    """)
    
    # Clear chat button
    if st.sidebar.button("Clear Chat History"):
        st.session_state.messages = []
        st.session_state.graph_state = None
        st.rerun()

if __name__ == "__main__":
    main()
