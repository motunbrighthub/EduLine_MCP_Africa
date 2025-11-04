# 🎓 EDULINE - Adaptive AI-Powered Quiz Platform

**The Offline AI Tutor for High School Students**

EDULINE is an adaptive learning platform that combines intelligent quiz systems with AI-powered tutoring to help students master difficult concepts. When students struggle with a topic, they can instantly get personalized explanations from an AI tutor powered by OpenAI's GPT-4.

[![Deploy to Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io)

---

##  Table of Contents

- [Features](#-features)
- [How It Works](#-how-it-works)
- [MCP Architecture](#-mcp-architecture)
- [Installation](#-installation)
- [Running the Application](#-running-the-application)
- [MCP Integration](#-mcp-integration)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Deployment](#-deployment)
- [Usage Guide](#-usage-guide)
- [Contributing](#-contributing)
- [License](#-license)

---

##  Features

###  Adaptive Quiz System
- **Dynamic Difficulty**: Questions adapt based on student performance
- **Multi-Subject**: Mathematics, Chemistry, Physics, English
- **Cluster-Based Topics**: 9 difficulty levels (0-8) per subject
- **Progress Tracking**: Real-time monitoring of weak areas

###  AI Tutor Integration (MCP)
- **Context-Aware Help**: AI knows exactly which topic the student struggled with
- **Personalized Explanations**: Adapts to urban/rural context for relevant examples
- **Conversational Learning**: Multi-turn dialogue for deeper understanding
- **On-Demand Support**: Help appears when students need it most

###  Student Management
- **Secure Login**: Password-protected student accounts
- **Unique Student IDs**: Auto-generated EDU-XXXXXXXX format
- **Progress History**: View past quiz results and improvements
- **Weak Area Tracking**: Identify and retry problem topics

###  Analytics
- **Performance Metrics**: Score tracking across subjects
- **Weak Cluster Detection**: Automatic identification of struggling topics
- **Historical Data**: SQLite database stores all student progress

---

##  How It Works

### The Learning Flow:

```
1. Student Registration → Unique ID + Password
2. Subject Selection → Choose Math/Chemistry/Physics/English
3. Adaptive Quiz → Questions adjust to performance
4. Wrong Answer? → AI Tutor button appears
5. Ask AI → Get personalized explanation
6. Follow-up Questions → Continue until concept is clear
7. Results & Analytics → View weak areas
8. Targeted Practice → Retry weak topics mode
```

### Adaptive Algorithm:

- **Correct Answer**: Move to higher difficulty cluster (+1)
- **Wrong Answer**: Move to lower difficulty cluster (-1)
- **Cluster Range**: 0 (easiest) to 8 (hardest)
- **Smart Sampling**: Never repeats same question in a session

---

##  MCP Architecture

### What is MCP?

**Model Context Protocol (MCP)** is the system that connects our quiz data with OpenAI's GPT-4 to provide intelligent, context-aware tutoring.

### MCP Flow Diagram:

```
┌─────────────┐
│   Student   │
│  Takes Quiz │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Wrong?    │ ──Yes──> ┌────────────────┐
└─────────────┘          │  MCP Context   │
                         │  Preparation   │
                         └────────┬───────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │  System Prompt │
                         │  + Topic Info  │
                         │  + Chat History│
                         └────────┬───────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │  OpenAI API    │
                         │  (GPT-4o-mini) │
                         └────────┬───────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │  AI Response   │
                         │  Generated     │
                         └────────┬───────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │  Chat Interface│
                         │  (Student sees)│
                         └────────────────┘
```

### MCP Context Payload:

When a student requests help, the MCP layer prepares:

```python
{
  "subject": "Physics",
  "topic": "Electricity, Sound & Current",
  "cluster_id": 5,
  "student_level": "High school",
  "location": "Urban" | "Rural",
  "conversation_history": [...previous messages],
  "system_prompt": "You are EDULINE's AI tutor..."
}
```

### Why MCP is Creative:

1. **Precision Targeting**: AI knows EXACTLY which concept failed (not just "Physics")
2. **Context Personalization**: Examples adapt to student's urban/rural setting
3. **Memory**: Maintains conversation history for coherent follow-ups
4. **Cost Efficiency**: Only calls API when help is requested (~$0.001/session)
5. **Offline-First**: Quiz works without internet; AI is enhancement

---

##  Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- OpenAI API key ([Get one here](https://platform.openai.com/api-keys))

### Step 1: Clone the Repository

```bash
git clone https://github.com/motunhub/eduline-app.git
cd eduline-app
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate

# On macOS/Linux:
source venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt contents:**
```txt
streamlit==1.31.0
pandas==2.1.4
openai==1.12.0
```

### Step 4: Set Up OpenAI API Key

**Option A: Environment Variable**
```bash
# Linux/macOS
export OPENAI_API_KEY="sk-proj-your-key-here"

# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-proj-your-key-here"

# Windows (CMD)
set OPENAI_API_KEY=sk-proj-your-key-here
```

**Option B: Streamlit Secrets (Production)**

Create `.streamlit/secrets.toml`:
```toml
OPENAI_API_KEY = "sk-proj-your-key-here"
```

 **Never commit your API key to GitHub!**

---

##  Running the Application

### Local Development

```bash
# Make sure you're in the project directory
cd eduline-app

# Run the Streamlit app
streamlit run app.py
```

The app will open in your browser at: `http://localhost:8501`

### First Time Setup

1. **Register**: Create a student account (you'll get an EDU-XXXXXXXX ID)
2. **Save your ID**: You'll need it to login
3. **Select Subject**: Choose from Math, Chemistry, Physics, English
4. **Start Quiz**: Take 5-20 questions (adjust slider)
5. **Get Help**: Click " Ask AI Tutor" when you get something wrong

---

##  MCP Integration

### How to Use the AI Tutor (MCP)

The AI tutor is automatically available when you answer incorrectly. Here's what happens behind the scenes:

### 1. MCP Context Preparation

When you click " Ask AI Tutor for Help":

```python
# System captures:
topic = "Logarithms (log₁₀) & Formulas"  # From cluster mapping
subject = "Mathematics"
student_area = "Urban"  # From profile
conversation_history = []  # Previous chat messages
```

### 2. MCP API Call

```python
def get_ai_help(topic, subject, user_question, conversation_history):
    # Build context-rich system prompt
    system_prompt = f"""You are EDULINE's AI tutor for {subject}.
    Student is struggling with: {topic}
    Student location: {student_area}
    
    Your role:
    - Explain simply for high school level
    - Use real-world examples relevant to their setting
    - Be encouraging and patient
    """
    
    # Prepare messages with history
    messages = [
        {"role": "system", "content": system_prompt}
    ]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": user_question})
    
    # Call OpenAI API
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        max_tokens=800,
        temperature=0.7
    )
    
    return response.choices[0].message.content
```

### 3. Example MCP Interaction

**Student fails:** "Logarithms & Formulas" question

**System sends to OpenAI:**
```json
{
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "system",
      "content": "You are EDULINE's AI tutor for Mathematics. Student is struggling with: Logarithms (log₁₀) & Formulas. Student location: Rural..."
    },
    {
      "role": "user",
      "content": "Why do we need logarithms? I don't understand their purpose."
    }
  ]
}
```

**OpenAI returns:**
```
Think of logarithms as the "opposite" of exponents, like how division is the opposite of multiplication. 

If you're trying to figure out how many times you need to double your money to reach a goal, that's a logarithm problem! For example, if you invest 1000 Naira and it doubles every year, how many years until you have 8000 Naira? That's log₂(8) = 3 years.

In your rural area, think of it like this: If one bag of rice feeds 10 people, how many "tens" do you need to feed 1000 people? That's log₁₀(1000) = 3 bags needed...
```

---

##  Project Structure

```
eduline-app/
│
├── app.py                      # Main Streamlit application
├── questions_clus8.csv         # Question database with clusters
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── .gitignore                  # Files to ignore in git
│
├── .streamlit/
│   └── secrets.toml           # API keys 
│
├── eduline.db                 # SQLite database (auto-generated)
│
└── logo_favicon1.png          # App logo (optional)
```

### Key Files Explained:

**app.py**
- Main application logic
- Streamlit UI components
- MCP integration functions
- Quiz adaptive algorithm
- Database operations

**cleaned_mcqs_clustered.csv**
- Question bank for all subjects
- Columns: Question, Option A-D, Correct Answer, Subject, Cluster
- Cluster 0-8 represents difficulty levels

**eduline.db** (auto-created)
- SQLite database
- Tables: `users`, `results`
- Stores student profiles and quiz history

---

##  Configuration

### Cluster Topic Mapping

Each cluster (0-8) maps to specific topics per subject:

```python
CLUSTER_TOPICS = {
    0: {
        "Mathematics": "Algebra (Quadratics & Roots)",
        "Chemistry": "Coal & Combustion",
        "Physics": "Gas Properties",
        "English": "Formal Letters & Vocabulary"
    },
    # ... clusters 1-8
}
```

### MCP Settings

Adjust in `app.py`:

```python
# OpenAI Model
model = "gpt-4o-mini"  # Fast, cheap, good quality

# Response Length
max_tokens = 800  # ~600 words

# Creativity Level
temperature = 0.7  # Balanced (0=deterministic, 1=creative)

# Quiz Settings
DEFAULT_TOTAL_Q = 5  # Questions per quiz
CLUSTER_LIMITS = {"English": 8, "Mathematics": 8, ...}
MIN_CLUSTER = 0
```

---

##  Deployment

### Streamlit Cloud

**Pros:** Free, easy, automatic HTTPS

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect repository
4. Add secrets: `OPENAI_API_KEY = "..."`
5. Deploy!

**Result:** `https://eduline-yourname.streamlit.app`

### Option 2: Heroku
```

```

---

##  Usage Guide

### For Students:

1. **Register Account**
   - Enter name (optional) and select Urban/Rural
   - Create password
   - Save your Student ID (EDU-XXXXXXXX)

2. **Take a Quiz**
   - Login with your Student ID
   - Choose subject
   - Select number of questions (3-20)
   - Click " Start Adaptive Quiz"

3. **Get AI Help**
   - Answer a question
   - If wrong, click " Ask AI Tutor for Help"
   - Chat with AI about the topic
   - Ask follow-up questions
   - Return to quiz when ready

4. **Review Progress**
   - See final score and weak areas
   - Click "🎯 Practice Weak Areas" to retry
   - View past results in sidebar

### For Teachers/Admins:

**Viewing Student Data:**
```python
import sqlite3
conn = sqlite3.connect('eduline.db')

# All students
students = pd.read_sql_query("SELECT * FROM users", conn)

# Student results
results = pd.read_sql_query("SELECT * FROM results WHERE student_uuid='EDU-12345678'", conn)
```

**Adding Questions:**
Edit `cleaned_mcqs_clustered.csv`:
```csv
Question,Option A,Option B,Option C,Option D,Correct Answer,Subject,Cluster
"What is 2+2?",3,4,5,6,B,Mathematics,0
```

---

## 💰 Cost Breakdown

### OpenAI API Costs (GPT-4o-mini):

```
Input:  $0.15 per 1M tokens
Output: $0.60 per 1M tokens

Average Tutoring Session:
- Input: ~200 tokens (context + question)
- Output: ~300 tokens (explanation)
- Cost: ~$0.001 per session

Real-World Example:
- 100 students
- 2 quizzes/week each
- 20% request AI help
- 40 AI sessions/week
- Weekly cost: ~$0.04
- Monthly cost: ~$0.16
- Yearly cost: ~$2

Less than $2/year for 100 students! 🎉
```


```

### "AI responses are slow"
- GPT-4o-mini should respond in 1-3 seconds
- Check your internet connection
- Verify OpenAI API status: status.openai.com

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---


---

## 👥 Authors

**Adijat motunrayo oyetoke**
- GitHub: [@motunhub](https://github.com/motunhub)
- Email: adijatmotunrayooyetoke@gmail.com

---

## 🙏 Acknowledgments

- **OpenAI** for GPT-4 API
- **Streamlit** for the amazing framework
- **Anthropic** for MCP inspiration
- **Students** who inspired this project

---


---

##  Quick Start Summary

```bash
# 1. Clone
git clone https://github.com/yourusername/eduline-app.git
cd eduline-app

# 2. Install
pip install -r requirements.txt

# 3. Configure
export OPENAI_API_KEY="sk-proj-your-key"

# 4. Run
streamlit run app.py

# 5. Visit
# http://localhost:8501
```

---
EDULINE-SLIDE URL: https://docs.google.com/presentation/d/1V9o3PoPlCzZn_BJmr6mxNQnUpzvBnt3x/edit?usp=sharing&ouid=114517254146853387883&rtpof=true&sd=true
EDULINE VIDEO CURL: https://drive.google.com/file/d/1M4e8f4j6hG1l-6Cz0BOzSH4s4YOBuXIy/view?usp=drive_link

**Made with love for West African students**