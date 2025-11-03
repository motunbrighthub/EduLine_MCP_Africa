# mcp_server.py

import os
from typing import List, Dict, Optional
from fastmcp import FastMCP  # ✅ FIXED: Correct import
from groq import Groq

# Get API key from environment
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set for the MCP server.")

# Initialize FastMCP server
mcp = FastMCP("EduLineTutorServer")

# Initialize Groq Client
groq_client = Groq(api_key=GROQ_API_KEY)


@mcp.tool()
def tutor_explanation(
        topic: str,
        subject: str,
        user_question: Optional[str] = None,  # ✅ FIXED: Made optional with default
        conversation_history: Optional[List[Dict]] = None,  # ✅ FIXED: Made optional
        location: str = "general"
) -> str:
    """
    Provides a detailed, Nigeria high school-level explanation for a struggling student.

    Args:
        topic: The specific topic the student is struggling with
        subject: The subject area (Mathematics, Chemistry, Physics, English)
        user_question: The student's specific question (optional)
        conversation_history: Previous chat messages for context (optional)
        location: Student's location (Urban/Rural) for relevant examples

    Returns:
        AI-generated explanation tailored to the student
    """

    # Build system prompt with location context
    system_prompt = f"""You are EDULINE's AI tutor helping a student understand {subject} concepts. 
The student is struggling with: {topic}
Student's setting: {location}

Your role:
- Break down complex concepts into simple, easy-to-understand explanations
- Use real-world examples and analogies relevant to a {location} setting in Nigeria
- Be encouraging and patient
- Adapt to high school level understanding
- Keep responses concise (2-3 paragraphs max unless asked for more detail)
- Use clear formatting with bullet points when listing steps or concepts

Remember: You're helping a Nigerian high school student who just got a question wrong. Be empathetic and build their confidence!
"""

    # Default question if none provided
    if user_question is None:
        user_question = f"Can you explain {topic} in {subject} in a simple way? I'm having trouble understanding it."

    # Build messages array
    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history if provided
    if conversation_history:
        messages.extend(conversation_history)

    # Add current user question
    messages.append({"role": "user", "content": user_question})


    try:
        response = mcp_client.call_tool(
            name="tutor_explanation",
            model="llama-3.3-70b-versatile",
            arguments={"topic": topic, "subject": subject},

        return response.choices[0].message.content

    except Exception as e:
        # Better error messages
        error_msg = str(e)
        if "rate_limit" in error_msg.lower():
            return "⏳ Too many students using the tutor right now. Please wait a moment and try again."
        elif "api_key" in error_msg.lower():
            return "🔒 Authentication error. Please contact your teacher."
        else:
            return f"❌ Sorry, I couldn't generate a response. Error: {error_msg[:100]}"


@mcp.tool()
def health_check() -> str:
    """
    Check if the AI tutor service is running properly.

    Returns:
        Status message
    """
    try:
        # Quick test call
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10
        )
        return "✅ EduLine AI Tutor is healthy and ready to help students!"
    except Exception as e:
        return f"⚠️ Service issue: {str(e)}"


@mcp.tool()
def get_study_tips(topic: str, subject: str) -> str:
    """
    Get study tips and resources for a specific topic.

    Args:
        topic: The topic to get tips for
        subject: The subject area

    Returns:
        Study tips and resources
    """
    return f"""📚 **Study Tips for {topic} in {subject}**

**How to Master This Topic:**
1. 📝 Practice problems regularly (start with easy ones)
2. 🎨 Create visual aids or diagrams
3. 👥 Teach the concept to a friend or family member
4. 🌍 Connect it to real-world Nigerian examples
5. 🔄 Break it into smaller sub-topics

**Next Steps:**
- Review the basics of this topic
- Try 5-10 practice problems
- Ask specific questions about what confuses you
- Return to EDULINE to retry weak areas

**Remember:** Every expert was once a beginner. Keep practicing! 
"""


# Run the server
if __name__ == "__main__":
    mcp.run()