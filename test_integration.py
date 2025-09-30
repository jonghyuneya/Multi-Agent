#!/usr/bin/env python3
"""
Test script to verify the integration between graphBuilder, tools, and streamlit_app
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_integration():
    """Test the complete workflow integration"""
    try:
        print("Testing integration...")
        
        # Test 1: Import all modules
        print("1. Testing imports...")
        from graphBuilder import graph
        from tools import tools, llm_with_tools
        from classes import AgentState
        print("   ✓ All imports successful")
        
        # Test 2: Test AgentState creation
        print("2. Testing AgentState creation...")
        test_state = AgentState(
            summary="",
            context="",
            query="test query",
            user_question="What is artificial intelligence?"
        )
        print(f"   ✓ AgentState created: {test_state.user_question}")
        
        # Test 3: Test tools
        print("3. Testing tools...")
        print(f"   ✓ Available tools: {[tool.name for tool in tools]}")
        
        # Test 4: Test graph compilation
        print("4. Testing graph compilation...")
        print(f"   ✓ Graph compiled successfully")
        print(f"   ✓ Graph nodes: {list(graph.get_graph().nodes.keys())}")
        
        print("\n🎉 All integration tests passed!")
        print("\nTo run the Streamlit app:")
        print("1. Activate your virtual environment: source fresh-venv/bin/activate")
        print("2. Install dependencies: pip install -r install.txt")
        print("3. Run: streamlit run streamlit_app.py")
        
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_integration())
    sys.exit(0 if success else 1)
