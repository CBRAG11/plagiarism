from pydantic import BaseModel, Field
from typing import List

class MCQ(BaseModel):
    question_text: str = Field(..., description="The question prompt")
    options: List[str] = Field(
        ...,
        min_items=4, max_items=4,
        description="Exactly 4 options, each like 'A. Answer text'"
    )
    answer: str = Field(
        ...,
        pattern="^[ABCD]$",
        description="The correct option, one of 'A','B','C','D'"
    )
    explanation: str = Field(
        "",
        description="Neutral comments / explanation for feedback"
    )


class AssignQuizRequest(BaseModel):
    course_id: int = Field(..., description="Canvas course ID")
    submission_id: str = Field(...,
                               description="Submission identifier for naming")
    questions: List[MCQ] = Field(..., description="List of MCQs to add")


class AssignQuizResponse(BaseModel):
    quiz_id: int
    created_questions: int
