#!/usr/bin/env python3
"""
Script to run the Streamlit orchestrator app
"""

import subprocess
import sys
import os

def run_streamlit():
    """Run the Streamlit app"""
    try:
        # Change to the script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        # Run streamlit
        cmd = [sys.executable, "-m", "streamlit", "run", "streamlit_app.py", "--server.port", "8501"]
        subprocess.run(cmd)
    except Exception as e:
        print(f"Error running Streamlit: {e}")
        print("Make sure you have installed all dependencies:")
        print("pip install streamlit")

if __name__ == "__main__":
    run_streamlit()
