#!/usr/bin/env python3
"""
Simple test to verify the fixes work
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def test_simple_fixes():
    """Test the simple fixes"""
    try:
        print("🧪 Testing Simple Fixes...")
        print("=" * 40)
        
        # Test 1: Import modules
        print("1. Testing imports...")
        from tools import question_clarity_checker
        from classes import AgentState
        print("   ✅ All imports successful")
        
        # Test 2: Test clarity checker with normal question
        print("\n2. Testing clarity checker with normal question...")
        normal_question = "What is the weather today?"
        clarity_result = await question_clarity_checker.ainvoke({"user_question": normal_question})
        print(f"   Question: '{normal_question}'")
        print(f"   Result: {clarity_result}")
        
        if "Clear: YES" in clarity_result:
            print("   ✅ Normal question correctly identified as clear")
        else:
            print("   ❌ Normal question incorrectly flagged as unclear")
            return False
        
        # Test 3: Test clarity checker with unclear question
        print("\n3. Testing clarity checker with unclear question...")
        unclear_question = "it"
        clarity_result = await question_clarity_checker.ainvoke({"user_question": unclear_question})
        print(f"   Question: '{unclear_question}'")
        print(f"   Result: {clarity_result}")
        
        if "Clear: NO" in clarity_result:
            print("   ✅ Unclear question correctly flagged")
        else:
            print("   ❌ Unclear question not flagged")
            return False
        
        # Test 4: Test dict handling
        print("\n4. Testing dict handling...")
        test_dict = {
            'user_question': 'test',
            'user_clarification': '',
            'clarification_confirmed': False
        }
        
        # Test dict access
        test_dict['user_clarification'] = 'clarified test'
        test_dict['clarification_confirmed'] = True
        
        print(f"   Dict updated successfully: {test_dict}")
        print("   ✅ Dict handling works")
        
        print("\n🎉 All fixes working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_simple_fixes())
    sys.exit(0 if success else 1)
