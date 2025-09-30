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
if "waiting_for_clarification" not in st.session_state:
    st.session_state.waiting_for_clarification = False
if "clarification_question" not in st.session_state:
    st.session_state.clarification_question = ""
if "current_agent_state" not in st.session_state:
    st.session_state.current_agent_state = None

def get_current_time_info():
    """Get current time information in Asia/Seoul timezone"""
    seoul_tz = pytz.timezone('Asia/Seoul')
    now = datetime.now(seoul_tz)
    return f"Current Time: {now.strftime('%Y-%m-%d %H:%M:%S KST')}"

async def process_user_question(user_question: str, is_clarification: bool = False):
    """Process user question through the orchestrator workflow"""
    try:
        print(f"process_user_question called with: '{user_question}', is_clarification: {is_clarification}")
        
        # If this is a clarification response, update the existing state
        if is_clarification and st.session_state.current_agent_state:
            print("Processing clarification response...")
            agent_state = st.session_state.current_agent_state
            agent_state.user_clarification = user_question
            agent_state.clarification_confirmed = True
            agent_state.needs_clarification = False
            print(f"Updated agent state with clarification: '{user_question}'")
        else:
            print("Creating new agent state...")
            # Create initial AgentState
            agent_state = AgentState(
                summary="",
                context="",
                query="",
                user_question=user_question,
                needs_clarification=False,
                clarification_question="",
                user_clarification="",
                clarification_confirmed=False
            )
        
        print(f"Agent state before processing: user_question='{agent_state.user_question}', user_clarification='{agent_state.user_clarification}', clarification_confirmed={agent_state.clarification_confirmed}")
        
        # Process through the graph
        config = {"configurable": {"thread_id": "user_session"}}
        
        # Run the graph with proper state format
        result = await graph.ainvoke(
            agent_state,
            config=config
        )
        
        print(f"Graph result: {type(result)}")
        if hasattr(result, 'needs_clarification'):
            print(f"Result needs_clarification: {result.needs_clarification}")
        if hasattr(result, 'query'):
            print(f"Result query: {result.query}")
        if hasattr(result, 'summary'):
            print(f"Result summary: {result.summary[:100] if result.summary else 'None'}...")
        
        return result
    except Exception as e:
        print(f"Error in process_user_question: {str(e)}")
        import traceback
        traceback.print_exc()
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
    chat_placeholder = "What would you like to know?"
    if st.session_state.waiting_for_clarification:
        chat_placeholder = "Please provide clarification for the question above..."
    
    if prompt := st.chat_input(chat_placeholder):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Process the question
        with st.chat_message("assistant"):
            with st.spinner("Processing your question..."):
                try:
                    # Determine if this is a clarification response
                    is_clarification = st.session_state.waiting_for_clarification
                    
                    print(f"Processing input: '{prompt}'")
                    print(f"Is clarification: {is_clarification}")
                    print(f"Current state - waiting_for_clarification: {st.session_state.waiting_for_clarification}")
                    
                    # Run async function
                    result = asyncio.run(process_user_question(prompt, is_clarification))
                    
                    if result:
                        # Check if result needs clarification
                        needs_clarification = False
                        clarification_question = ""
                        
                        if isinstance(result, dict):
                            needs_clarification = result.get('needs_clarification', False)
                            clarification_question = result.get('clarification_question', "")
                        elif hasattr(result, 'needs_clarification'):
                            needs_clarification = result.needs_clarification
                            clarification_question = result.clarification_question
                        
                        if needs_clarification and clarification_question:
                            # Show clarification request
                            st.warning(f"**🤔 Clarification Needed:**\n\n{clarification_question}")
                            
                            # Update session state
                            st.session_state.waiting_for_clarification = True
                            st.session_state.clarification_question = clarification_question
                            st.session_state.current_agent_state = result
                            
                            # Add clarification request to chat history
                            st.session_state.messages.append({"role": "assistant", "content": f"**🤔 Clarification Needed:**\n\n{clarification_question}"})
                            
                        else:
                            # Process normal response
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
                            
                            # Reset clarification state
                            st.session_state.waiting_for_clarification = False
                            st.session_state.clarification_question = ""
                            st.session_state.current_agent_state = None
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
    
    2. **🤔 Clarity Check** → Check if question is clear and specific
    
    3. **❓ Clarification** → If unclear, ask user for clarification
    
    4. **🔍 Typo Check** → Check for typos using typo service
    
    5. **🎯 Intent Classification** → Extract search query from intent
    
    6. **🔎 Naver API Search** → Search for data using the query
    
    7. **📰 Get Context** → Store search results as context
    
    8. **📝 Summarize** → Summarize context for final response
    
    9. **🤖 Deliver Response** → Show summary with sources
    """)
    
    # Clear chat button
    if st.sidebar.button("Clear Chat History"):
        st.session_state.messages = []
        st.session_state.graph_state = None
        st.session_state.waiting_for_clarification = False
        st.session_state.clarification_question = ""
        st.session_state.current_agent_state = None
        st.rerun()

if __name__ == "__main__":
    main()
