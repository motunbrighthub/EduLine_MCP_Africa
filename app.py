import streamlit as st
import pandas as pd
import random
import sqlite3
import json
import uuid
from datetime import datetime
from typing import Dict, List
import os
import google.generativeai as genai

# ==============================
# Config
# ==============================
st.set_page_config(
    page_title="EDULINE Adaptive Quiz",
    page_icon="📚",
    layout="centered",
)

# Fix: Use __file__ for path detection
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_CSV = os.path.join(BASE_DIR, "cleaned_mcqs_clustered.csv")
DB_PATH = "eduline.db"
DEFAULT_TOTAL_Q = 5
CLUSTER_LIMITS = {"English": 8, "Mathematics": 8, "Physics": 8, "Chemistry": 8}
MIN_CLUSTER = 0
MCP_AVAILABLE = False
GEMINI_MODEL_NAME = "gemini-2.5-flash"

# AI Tutor Setup
try:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        if "GOOGLE_API_KEY" in st.secrets:
            api_key = st.secrets["GOOGLE_API_KEY"]
    
    if api_key:
        genai.configure(api_key=api_key)
        gemini_client = genai.GenerativeModel(GEMINI_MODEL_NAME)
        MCP_AVAILABLE = True
    else:
        st.warning("API_KEY not found. AI Tutor will be disabled.")
except Exception as e:
    st.error(f"AI Tutor initialization failed: {e}")
    MCP_AVAILABLE = False

CLUSTER_TOPICS = {
    0: {"English": "Formal Letters & Vocabulary", "Mathematics": "Algebra (Quadratics & Roots)", "Physics": "Gas Properties", "Chemistry": "Coal & Combustion"},
    1: {"English": "Speech Forms & Simplification", "Mathematics": "Simplification & Expressions", "Physics": "General Concepts", "Chemistry": "Carbon & Oxides"},
    2: {"English": "Synonyms & Vocabulary", "Mathematics": "Terms & Differences", "Physics": "Units & Measurements", "Chemistry": "Acids & Reactions"},
    3: {"English": "Essay Writing & Summary", "Mathematics": "General Concepts", "Physics": "General Concepts", "Chemistry": "Industrial Processes & Raw Materials"},
    4: {"English": "Idioms & Word Choice", "Mathematics": "Sequences (GP) & Terms", "Physics": "Gas Processes", "Chemistry": "General Concepts"},
    5: {"English": "Advanced Vocabulary", "Mathematics": "Algebra (x², 2x) & Variation", "Physics": "Electricity, Sound & Current", "Chemistry": "Salts"},
    6: {"English": "Phrasal Verbs & Word Meanings", "Mathematics": "Logarithms (log₁₀) & Formulas", "Physics": "Heat", "Chemistry": "General Concepts"},
    7: {"English": "Antonyms & Opposites", "Mathematics": "Geometry (Area, Radius, Height)", "Physics": "General Concepts", "Chemistry": "Compounds"},
    8: {"English": "Multiple Choice Vocabulary", "Mathematics": "Probability & Numbers", "Physics": "General Concepts", "Chemistry": "Ions & Trioxocarbonates"}
}

# ==============================
# Database Utils
# ==============================
def init_db(path=DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_uuid TEXT UNIQUE,
            name TEXT,
            area TEXT,
            password TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_uuid TEXT,
            subject TEXT,
            score INTEGER,
            total_questions INTEGER,
            progress REAL,
            weak_clusters_json TEXT,
            taken_at TEXT
        )
    """)
    conn.commit()
    return conn

def insert_user(conn, student_uuid: str, name: str, area: str, password: str):
    cur = conn.cursor()
    cur.execute("INSERT INTO users (student_uuid, name, area, password, created_at) VALUES (?, ?, ?, ?, ?)",
                (student_uuid, name, area, password, datetime.now().isoformat()))
    conn.commit()

def verify_login(conn, student_uuid: str, password: str):
    cur = conn.cursor()
    result = cur.execute("SELECT student_uuid, name, area FROM users WHERE student_uuid=? AND password=?",
                         (student_uuid, password)).fetchone()
    return result

def save_result(conn, student_uuid: str, subject: str, score: int, total_questions: int, progress: float, weak_clusters: dict):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO results (student_uuid, subject, score, total_questions, progress, weak_clusters_json, taken_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (student_uuid, subject, score, total_questions, progress, json.dumps(weak_clusters), datetime.now().isoformat()))
    conn.commit()

conn = init_db(DB_PATH)

# ==============================
# Load Questions
# ==============================
@st.cache_data
def load_questions(path):
    if not os.path.exists(path):
        # Create a dummy dataframe if file doesn't exist for testing
        return pd.DataFrame(columns=["Subject", "Cluster", "Question", "Option A", "Option B", "Option C", "Option D", "Answer"])
    df = pd.read_csv(path)
    df["Cluster"] = df["Cluster"].astype(int)
    return df

df_all = load_questions(QUESTIONS_CSV)

# ==============================
# Session State Init
# ==============================
if "app" not in st.session_state:
    st.session_state.app = {"stage": "auth", "auth_mode": "login", "student_uuid": None, "name": "", "area": ""}

if "quiz" not in st.session_state:
    st.session_state.quiz = {
        "started": False, "subject": None, "cluster": 0, "question_index": 0,
        "total_questions": DEFAULT_TOTAL_Q, "score": 0, "used_indices": [],
        "current_question": None, "submitted": False, "feedback": "",
        "weak_clusters": {}, "mode": "normal", "weak_only_list": []
    }

if "chat" not in st.session_state:
    st.session_state.chat = {"messages": [], "active_topic": None, "active_subject": None}

app = st.session_state.app
quiz = st.session_state.quiz
chat = st.session_state.chat

# ==============================
# Helpers
# ==============================
def gen_uuid() -> str:
    return "EDU-" + str(uuid.uuid4())[:8].upper()

def get_cluster_topic(subject: str, cluster_id: int) -> str:
    if cluster_id in CLUSTER_TOPICS and subject in CLUSTER_TOPICS[cluster_id]:
        return CLUSTER_TOPICS[cluster_id][subject]
    return f"Cluster {cluster_id}"

def reset_quiz_state(subject: str, total_q: int, mode: str = "normal", weak_only_list: List[int] = None):
    mid = CLUSTER_LIMITS.get(subject, 4) // 2
    start_cluster = mid if mode == "normal" else (weak_only_list[0] if weak_only_list else mid)
    quiz.update({
        "started": True, "subject": subject, "cluster": start_cluster, "question_index": 0,
        "total_questions": total_q, "score": 0, "used_indices": [], "current_question": None,
        "submitted": False, "feedback": "", "weak_clusters": {} if mode == "normal" else {c: 0 for c in (weak_only_list or [])},
        "mode": mode, "weak_only_list": weak_only_list or []
    })

def load_next_question():
    df_subj = df_all[df_all["Subject"] == quiz["subject"]].reset_index(drop=True)
    target_cluster = quiz["cluster"]

    if quiz["mode"] == "weak_only" and quiz["weak_only_list"]:
        if target_cluster not in quiz["weak_only_list"]:
            target_cluster = random.choice(quiz["weak_only_list"])
            quiz["cluster"] = target_cluster

    subset = df_subj[df_subj["Cluster"] == target_cluster].drop(quiz["used_indices"], errors="ignore")

    if subset.empty:
        if quiz["mode"] == "weak_only" and quiz["weak_only_list"]:
            subset = df_subj[df_subj["Cluster"].isin(quiz["weak_only_list"])].drop(quiz["used_indices"], errors="ignore")
        else:
            subset = df_subj.drop(quiz["used_indices"], errors="ignore")

    if subset.empty:
        return False

    q = subset.sample(1).iloc[0]
    quiz["current_question"] = q
    quiz["used_indices"].append(q.name)
    quiz["submitted"] = False
    quiz["feedback"] = ""
    return True

def submit_answer(choice_key: str):
    q = quiz["current_question"]
    correct = str(q["Answer"]).strip().upper()
    cluster_at_time = quiz["cluster"]

    if choice_key == correct:
        quiz["score"] += 1
        if quiz["mode"] == "normal":
            quiz["cluster"] = min(CLUSTER_LIMITS.get(quiz["subject"], 8), quiz["cluster"] + 1)
        quiz["feedback"] = "✅ Correct! Great job."
    else:
        if quiz["mode"] == "normal":
            quiz["cluster"] = max(MIN_CLUSTER, quiz["cluster"] - 1)
        quiz["feedback"] = f"❌ Wrong! Correct answer: {correct}"
        quiz["weak_clusters"][cluster_at_time] = quiz["weak_clusters"].get(cluster_at_time, 0) + 1
    quiz["submitted"] = True

def finish_and_record():
    progress_ratio = quiz["question_index"] / max(1, quiz["total_questions"])
    try:
        save_result(conn, app["student_uuid"], quiz["subject"], quiz["score"],
                    quiz["total_questions"], progress_ratio, quiz["weak_clusters"])
    except Exception as e:
        st.warning(f"Could not save results to DB: {e}")
    quiz["started"] = False
    app["stage"] = "finished"

def get_ai_help(topic: str, subject: str, user_question: str = None, conversation_history: List[Dict] = None):
    if not MCP_AVAILABLE:
        return "AI tutor is not available. Please set up GOOGLE_API_KEY."
    
   system_prompt = f"""
You are EDULINE's AI tutor helping a student understand {subject}.

The student is struggling with: {topic}.

Instructions:
- Explain concepts step-by-step.
- Start with a simple definition.
- Break complex ideas into smaller parts.
- Use real-world examples relevant to a {app.get('area', 'general')} setting.
- Include worked examples when appropriate.
- Explain any formulas or calculations involved.
- End with a short summary.
- Aim for 5-8 detailed paragraphs when necessary.
- Adapt the depth of explanation to the student's question.
"""

    try:
        full_prompt = f"{system_prompt}\n\nStudent Question: {user_question}"
        response = gemini_client.generate_content(
            full_prompt,
            generation_config=genai.types.GenerationConfig(max_output_tokens=2000, temperature=0.7)
        )
        return response.text
    except Exception as e:
        return f"Sorry, I couldn't generate a response: {str(e)}"

# Global Logout
if app["student_uuid"]:
    if st.sidebar.button("Logout"):
        app.update({"stage": "auth", "student_uuid": None, "name": "", "area": ""})
        st.rerun()

# ==============================
# STAGE: Auth
# ==============================
if app["stage"] == "auth":
    tab1, tab2 = st.tabs(["Login", "Register"])
    with tab1:
        st.markdown("### Welcome back!")
        login_id = st.text_input("Student ID", key="login_id")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Login", type="primary"):
            res = verify_login(conn, login_id, login_pass)
            if res:
                app.update({"student_uuid": res[0], "name": res[1], "area": res[2], "stage": "subject"})
                st.rerun()
            else:
                st.error("Invalid credentials")

    with tab2:
        st.markdown("### Create Profile")
        reg_name = st.text_input("Name", key="reg_name")
        reg_area = st.radio("Location", ["Urban", "Rural"])
        reg_pass = st.text_input("Password", type="password", key="reg_pass")
        if st.button("Create Account"):
            uid = gen_uuid()
            insert_user(conn, uid, reg_name, reg_area, reg_pass)
            st.success(f"Created! ID: {uid}")
            app.update({"student_uuid": uid, "name": reg_name, "area": reg_area, "stage": "subject"})
            st.rerun()

# ==============================
# STAGE: Subject Selection
# ==============================
elif app["stage"] == "subject":
    st.title(f"Hello, {app['name']}!")
    allowed_subjects = ["English", "Mathematics", "Physics", "Chemistry"]
    subject = st.selectbox("Select Subject", allowed_subjects)
    total_q = st.slider("Questions", 3, 20, DEFAULT_TOTAL_Q)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Start Quiz", type="primary"):
            reset_quiz_state(subject, total_q)
            app["stage"] = "quiz"
            st.rerun()
    with col2:
        has_weak = any(v > 0 for v in quiz.get("weak_clusters", {}).values())
        if st.button("Retry Weak Areas", disabled=not has_weak):
            weak_list = [c for c, m in quiz["weak_clusters"].items() if m > 0]
            reset_quiz_state(subject, total_q, mode="weak_only", weak_only_list=weak_list)
            app["stage"] = "quiz"
            st.rerun()

# ==============================
# STAGE: Quiz
# ==============================
elif app["stage"] == "quiz":
    if quiz["current_question"] is None:
        if not load_next_question():
            st.warning("No more questions!")
            finish_and_record()
            st.rerun()

    q = quiz["current_question"]
    topic_name = get_cluster_topic(quiz["subject"], quiz["cluster"])
    
    st.subheader(f"{quiz['subject']} - Question {quiz['question_index'] + 1}")
    st.info(f"Topic: {topic_name}")
    st.progress(quiz["question_index"] / quiz["total_questions"])
    
    st.write(q["Question"])
    opts = {"A": q["Option A"], "B": q["Option B"], "C": q["Option C"], "D": q["Option D"]}
    choice = st.radio("Answer:", list(opts.keys()), format_func=lambda k: f"{k}. {opts[k]}")

    if not quiz["submitted"]:
        if st.button("Submit Answer"):
            submit_answer(choice)
            st.rerun()
    else:
        if "✅" in quiz["feedback"]:
            st.success(quiz["feedback"])
        else:
            st.error(quiz["feedback"])
            if MCP_AVAILABLE and st.button("Ask AI Tutor"):
                chat.update({"active_topic": topic_name, "active_subject": quiz["subject"], "messages": []})
                app["stage"] = "help"
                st.rerun()
        
        if st.button("Next Question"):
            quiz["question_index"] += 1
            if quiz["question_index"] >= quiz["total_questions"]:
                finish_and_record()
            else:
                quiz["current_question"] = None
                quiz["submitted"] = False
            st.rerun()

# ==============================
# STAGE: AI Help
# ==============================
elif app["stage"] == "help":
    st.title("AI Tutor")
    for m in chat["messages"]:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("Ask a question..."):
        chat["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            resp = get_ai_help(chat["active_topic"], chat["active_subject"], prompt, chat["messages"][:-1])
            st.markdown(resp)
            chat["messages"].append({"role": "assistant", "content": resp})
        st.rerun()
    
    if st.button("Back to Quiz"):
        app["stage"] = "quiz"
        st.rerun()

# ==============================
# STAGE: Finished
# ==============================
elif app["stage"] == "finished":
    st.balloons()
    st.header("Quiz Complete!")
    st.metric("Score", f"{quiz['score']}/{quiz['total_questions']}")
    if st.button("Main Menu"):
        app["stage"] = "subject"
        st.rerun()
