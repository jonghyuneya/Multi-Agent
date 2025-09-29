from pydantic import BaseModel, Field
from typing import Optional

class AgentState(BaseModel):
    summary: str
    context: str = Field(description="information obtained from NaverAPI")
    query: str = Field(description="subject to research")
    user_question: str  # query
    
    # Time tracking fields
    orchestrator_start_time: Optional[str] = None
    orchestrator_start_timestamp: Optional[float] = None
    orchestrator_end_time: Optional[str] = None
    orchestrator_end_timestamp: Optional[float] = None
    orchestrator_processing_time: Optional[float] = None 