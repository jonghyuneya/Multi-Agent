#!/usr/bin/env python3
"""
Test script to verify the complete user reply flow for clarification
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_user_reply_flow():
    """Test the complete user reply flow for clarification"""
    try:
        print("🧪 Testing Complete User Reply Flow...")
        print("=" * 60)
        
        # Test 1: Import modules
        print("1. Testing imports...")
        from graphBuilder import graph
        from classes import AgentState
        print("   ✅ All imports successful")
        
        # Test 2: Simulate unclear question -> clarification request
        print("\n2. Testing unclear question -> clarification request...")
        unclear_state = AgentState(
            summary="",
            context="",
            query="",
            user_question="it",
            needs_clarification=False,
            clarification_question="",
            user_clarification="",
            clarification_confirmed=False
        )
        
        config = {"configurable": {"thread_id": "test_unclear"}}
        result_unclear = await graph.ainvoke(unclear_state, config=config)
        
        print(f"   Unclear question result:")
        if isinstance(result_unclear, dict):
            needs_clarification = result_unclear.get('needs_clarification', False)
            clarification_question = result_unclear.get('clarification_question', "")
            print(f"     - needs_clarification: {needs_clarification}")
            print(f"     - clarification_question: {clarification_question}")
        else:
            needs_clarification = getattr(result_unclear, 'needs_clarification', False)
            clarification_question = getattr(result_unclear, 'clarification_question', "")
            print(f"     - needs_clarification: {needs_clarification}")
            print(f"     - clarification_question: {clarification_question}")
        
        if not needs_clarification:
            print("   ❌ Expected clarification request but didn't get one")
            return False
        
        print("   ✅ Clarification request generated successfully")
        
        # Test 3: Simulate user providing clarification -> continue processing
        print("\n3. Testing user clarification -> continue processing...")
        clarified_state = AgentState(
            summary="",
            context="",
            query="",
            user_question="it",  # Original unclear question
            needs_clarification=False,  # Reset after user provides clarification
            clarification_question="",
            user_clarification="What is artificial intelligence?",  # User's clarification
            clarification_confirmed=True  # User has provided clarification
        )
        
        config = {"configurable": {"thread_id": "test_clarified"}}
        result_clarified = await graph.ainvoke(clarified_state, config=config)
        
        print(f"   Clarified question result:")
        if isinstance(result_clarified, dict):
            needs_clarification = result_clarified.get('needs_clarification', False)
            query = result_clarified.get('query', "")
            summary = result_clarified.get('summary', "")
            print(f"     - needs_clarification: {needs_clarification}")
            print(f"     - query: {query}")
            print(f"     - summary: {summary[:100] if summary else 'None'}...")
        else:
            needs_clarification = getattr(result_clarified, 'needs_clarification', False)
            query = getattr(result_clarified, 'query', "")
            summary = getattr(result_clarified, 'summary', "")
            print(f"     - needs_clarification: {needs_clarification}")
            print(f"     - query: {query}")
            print(f"     - summary: {summary[:100] if summary else 'None'}...")
        
        if needs_clarification:
            print("   ❌ Still needs clarification after user provided it")
            return False
        
        if not query:
            print("   ❌ No query generated from clarification")
            return False
        
        print("   ✅ Clarification processed successfully")
        
        # Test 4: Test complete flow simulation
        print("\n4. Testing complete flow simulation...")
        
        # Step 1: User asks unclear question
        print("   Step 1: User asks unclear question 'it'")
        step1_state = AgentState(
            summary="", context="", query="", user_question="it",
            needs_clarification=False, clarification_question="", 
            user_clarification="", clarification_confirmed=False
        )
        
        result1 = await graph.ainvoke(step1_state, config={"configurable": {"thread_id": "flow_test"}})
        
        if isinstance(result1, dict):
            needs_clarification1 = result1.get('needs_clarification', False)
            clarification_question1 = result1.get('clarification_question', "")
        else:
            needs_clarification1 = getattr(result1, 'needs_clarification', False)
            clarification_question1 = getattr(result1, 'clarification_question', "")
        
        print(f"     Result: needs_clarification={needs_clarification1}")
        print(f"     Clarification question: {clarification_question1}")
        
        if not needs_clarification1:
            print("   ❌ Step 1 failed - should need clarification")
            return False
        
        # Step 2: User provides clarification
        print("   Step 2: User provides clarification 'What is AI?'")
        step2_state = AgentState(
            summary="", context="", query="", user_question="it",
            needs_clarification=False, clarification_question="",
            user_clarification="What is AI?", clarification_confirmed=True
        )
        
        result2 = await graph.ainvoke(step2_state, config={"configurable": {"thread_id": "flow_test"}})
        
        if isinstance(result2, dict):
            needs_clarification2 = result2.get('needs_clarification', False)
            query2 = result2.get('query', "")
            summary2 = result2.get('summary', "")
        else:
            needs_clarification2 = getattr(result2, 'needs_clarification', False)
            query2 = getattr(result2, 'query', "")
            summary2 = getattr(result2, 'summary', "")
        
        print(f"     Result: needs_clarification={needs_clarification2}")
        print(f"     Query: {query2}")
        print(f"     Summary: {summary2[:100] if summary2 else 'None'}...")
        
        if needs_clarification2:
            print("   ❌ Step 2 failed - still needs clarification")
            return False
        
        if not query2:
            print("   ❌ Step 2 failed - no query generated")
            return False
        
        print("   ✅ Complete flow simulation successful")
        
        print("\n🎉 User Reply Flow Test Completed Successfully!")
        print("\n📋 User Reply Flow Summary:")
        print("   1. ✅ Unclear questions trigger clarification request")
        print("   2. ✅ User can provide clarification response")
        print("   3. ✅ System processes clarification and continues workflow")
        print("   4. ✅ Query extraction works with clarified question")
        print("   5. ✅ Complete flow from unclear -> clarify -> process works")
        
        return True
        
    except Exception as e:
        print(f"❌ User reply flow test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_user_reply_flow())
    sys.exit(0 if success else 1)
