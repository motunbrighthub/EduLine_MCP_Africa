# mcp_server.py

import os
from typing import List, Dict
from fastmcp.server.fastmcp import FastMCP
from groq import Groq


GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set for the MCP server.")


mcp = FastMCP(
    name="EduLineTutorServer",
    instructions="Provides context-aware tutoring via Groq's high-speed Llama model."
)

# Initialize Groq Client securely
groq_client = Groq(api_key=GROQ_API_KEY)

@mcp.tool()
async def tutor_explanation(topic: str, subject: str, user_question: str, conversation_history: List[Dict], location: str = 'general') -> str:
    """Provides a detailed, Nigeria high school-level explanation for a struggling student."""

    # FIX: Use the 'location' argument instead of the undefined 'app.get(...)'
    system_prompt = f"""You are EDULINE's AI tutor helping a student understand {subject} concepts. 
    The student is struggling with: {topic}
     Your role:
    - Break down complex concepts into simple, easy-to-understand explanations
    - Use real-world examples and analogies relevant to a {location} setting
    - Be encouraging and patient
    - Adapt to high school level understanding
    - Keep responses concise (2-3 paragraphs max unless asked for more detail)
    - Use clear formatting with bullet points when listing steps or concepts
    """


    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_question})

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        # Log the full traceback or specific error for easier debugging
        return f"AI Generation Error: {str(e)}"


if __name__ == "__main__":
    # Ensure this runs on a public IP/port if you deploy it to a server (e.g., Vercel, Render)
    mcp.run()