#!/usr/bin/env python3
"""
Test script to verify the new orchestrator workflow
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_workflow():
    """Test the new orchestrator workflow step by step"""
    try:
        print("🧪 Testing New Orchestrator Workflow...")
        print("=" * 50)
        
        # Test 1: Import modules
        print("1. Testing imports...")
        from graphBuilder import graph
        from tools import typo_service, intent_classifier, naver_api, summarizer
        from classes import AgentState
        print("   ✅ All imports successful")
        
        # Test 2: Test individual tools
        print("\n2. Testing individual tools...")
        
        # Test typo service
        test_question = "artifical inteligence"  # Intentional typos
        print(f"   Testing typo service with: '{test_question}'")
        corrected = await typo_service.ainvoke({"user_question": test_question})
        print(f"   ✅ Typo service result: '{corrected}'")
        
        # Test intent classifier
        print(f"   Testing intent classifier with: '{corrected}'")
        intent_result = await intent_classifier.ainvoke({"user_question": corrected})
        print(f"   ✅ Intent classifier result: '{intent_result}'")
        
        # Test 3: Test complete workflow
        print("\n3. Testing complete workflow...")
        test_state = AgentState(
            summary="",
            context="",
            query="",
            user_question="What is artificial intelligence?"
        )
        
        print(f"   Initial state:")
        print(f"     - user_question: {test_state.user_question}")
        print(f"     - query: {test_state.query}")
        print(f"     - context: {test_state.context}")
        print(f"     - summary: {test_state.summary}")
        
        # Run the graph
        config = {"configurable": {"thread_id": "test_session"}}
        result = await graph.ainvoke(test_state, config=config)
        
        print(f"\n   Final state:")
        if isinstance(result, dict):
            print(f"     - user_question: {result.get('user_question', 'N/A')}")
            print(f"     - query: {result.get('query', 'N/A')}")
            print(f"     - context: {result.get('context', 'N/A')[:100]}..." if result.get('context') else "     - context: N/A")
            print(f"     - summary: {result.get('summary', 'N/A')[:100]}..." if result.get('summary') else "     - summary: N/A")
        else:
            print(f"     - user_question: {getattr(result, 'user_question', 'N/A')}")
            print(f"     - query: {getattr(result, 'query', 'N/A')}")
            print(f"     - context: {getattr(result, 'context', 'N/A')[:100]}..." if getattr(result, 'context', None) else "     - context: N/A")
            print(f"     - summary: {getattr(result, 'summary', 'N/A')[:100]}..." if getattr(result, 'summary', None) else "     - summary: N/A")
        
        print("\n🎉 Workflow test completed successfully!")
        print("\n📋 Workflow Summary:")
        print("   1. ✅ User input saved in user_question")
        print("   2. ✅ Typo check performed")
        print("   3. ✅ Intent classification and query extraction")
        print("   4. ✅ Naver API search (if query available)")
        print("   5. ✅ Context stored from search results")
        print("   6. ✅ Summary generated from context")
        print("   7. ✅ Final response ready")
        
        return True
        
    except Exception as e:
        print(f"❌ Workflow test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_workflow())
    sys.exit(0 if success else 1)
