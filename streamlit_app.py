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
    """Process user question through the orchestrator"""
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
            agent_state.dict(),
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
                        # Extract response from result - check for summary or other fields
                        if hasattr(result, 'summary') and result.summary:
                            response = result.summary
                        elif hasattr(result, 'context') and result.context:
                            response = result.context
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
    
    st.sidebar.markdown("### Instructions")
    st.sidebar.markdown("""
    1. Ask questions in Korean or English
    2. The system will automatically:
       - Fix typos if needed
       - Classify your intent
       - Search for information
       - Provide a summary
    3. Responses include sources and timestamps
    """)
    
    # Clear chat button
    if st.sidebar.button("Clear Chat History"):
        st.session_state.messages = []
        st.session_state.graph_state = None
        st.rerun()

if __name__ == "__main__":
    main()
