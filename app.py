# app.py
import streamlit as st
import pandas as pd
import random
import sqlite3
import json
import uuid
from datetime import datetime
from typing import Dict, List
import os

# 💡 IMPORTANT: Swapping OpenAI for Groq SDK
from groq import Groq  # <-- New Groq import

# ==============================
# Configuration
# ==============================
st.set_page_config(
    page_title="EDULINE Adaptive Quiz",
    page_icon="logo_favicon1.png",
    layout="centered",
)

BASE_DIR = os.path.dirname(__file__)

QUESTIONS_CSV = os.path.join(BASE_DIR, "cleaned_mcqs_clustered.csv")
DB_PATH = "eduline.db"
DEFAULT_TOTAL_Q = 5
CLUSTER_LIMITS = {"English": 8, "Mathematics": 8, "Physics": 8, "Chemistry": 8}
MIN_CLUSTER = 0

# Initialize Groq client (requires GROQ_API_KEY env variable)
try:
    # Try streamlit secrets first, then environment variable
    api_key = None
    try:
        api_key = st.secrets.get("GROQ_API_KEY")
    except:
        api_key = os.environ.get("GROQ_API_KEY")

    if api_key:
        groq_client = Groq(api_key=api_key)  # <-- Initialize Groq Client
        MCP_AVAILABLE = True  # Model Compute Provider available
    else:
        MCP_AVAILABLE = False
        st.warning("GROQ_API_KEY not found. AI Tutor will be disabled.")
except Exception as e:
    st.error(f"Groq initialization error: {e}")
    MCP_AVAILABLE = False

# ==============================
# CLUSTER TOPIC MAPPING
# ==============================
CLUSTER_TOPICS = {
    0: {
        "English": "Formal Letters & Vocabulary",
        "Mathematics": "Algebra (Quadratics & Roots)",
        "Physics": "Gas Properties",
        "Chemistry": "Coal & Combustion"
    },
    1: {
        "English": "Speech Forms & Simplification",
        "Mathematics": "Simplification & Expressions",
        "Physics": "General Concepts",
        "Chemistry": "Carbon & Oxides"
    },
    2: {
        "English": "Synonyms & Vocabulary",
        "Mathematics": "Terms & Differences",
        "Physics": "Units & Measurements",
        "Chemistry": "Acids & Reactions"
    },
    3: {
        "English": "Essay Writing & Summary",
        "Mathematics": "General Concepts",
        "Physics": "General Concepts",
        "Chemistry": "Industrial Processes & Raw Materials"
    },
    4: {
        "English": "Idioms & Word Choice",
        "Mathematics": "Sequences (GP) & Terms",
        "Physics": "Gas Processes",
        "Chemistry": "General Concepts"
    },
    5: {
        "English": "Advanced Vocabulary",
        "Mathematics": "Algebra (x², 2x) & Variation",
        "Physics": "Electricity, Sound & Current",
        "Chemistry": "Salts"
    },
    6: {
        "English": "Phrasal Verbs & Word Meanings",
        "Mathematics": "Logarithms (log₁₀) & Formulas",
        "Physics": "Heat",
        "Chemistry": "General Concepts"
    },
    7: {
        "English": "Antonyms & Opposites",
        "Mathematics": "Geometry (Area, Radius, Height)",
        "Physics": "General Concepts",
        "Chemistry": "Compounds"
    },
    8: {
        "English": "Multiple Choice Vocabulary",
        "Mathematics": "Probability & Numbers",
        "Physics": "General Concepts",
        "Chemistry": "Ions & Trioxocarbonates"
    }
}


# ==============================
# Database utils
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
    cur.execute("""
        INSERT INTO users (student_uuid, name, area, password, created_at) VALUES (?, ?, ?, ?, ?)
    """, (student_uuid, name, area, password, datetime.now().isoformat()))
    conn.commit()


def verify_login(conn, student_uuid: str, password: str):
    cur = conn.cursor()
    result = cur.execute("""
        SELECT student_uuid, name, area FROM users WHERE student_uuid=? AND password=?
    """, (student_uuid, password)).fetchone()
    return result


def save_result(conn, student_uuid: str, subject: str, score: int, total_questions: int, progress: float,
                weak_clusters: dict):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO results (student_uuid, subject, score, total_questions, progress, weak_clusters_json, taken_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (student_uuid, subject, score, total_questions, progress, json.dumps(weak_clusters),
          datetime.now().isoformat()))
    conn.commit()


# Initialize DB
conn = init_db(DB_PATH)


# ==============================
# Load questions
# ==============================
@st.cache_data
def load_questions(path):
    df = pd.read_csv(path)
    df["Cluster"] = df["Cluster"].astype(int)
    return df


df_all = load_questions(QUESTIONS_CSV)

# ==============================
# Session state init
# ==============================
if "app" not in st.session_state:
    st.session_state.app = {
        "stage": "auth",
        "auth_mode": "login",
        "student_uuid": None,
        "name": "",
        "area": "",
    }

if "quiz" not in st.session_state:
    st.session_state.quiz = {
        "started": False,
        "subject": None,
        "cluster": 0,
        "question_index": 0,
        "total_questions": DEFAULT_TOTAL_Q,
        "score": 0,
        "used_indices": [],
        "current_question": None,
        "submitted": False,
        "feedback": "",
        "weak_clusters": {},
        "mode": "normal",
        "weak_only_list": [],
    }

if "chat" not in st.session_state:
    st.session_state.chat = {
        "messages": [],
        "active_topic": None,
        "active_subject": None
    }

app = st.session_state.app
quiz = st.session_state.quiz
chat = st.session_state.chat


# ==============================
# Helpers
# ==============================
def gen_uuid() -> str:
    return "EDU-" + str(uuid.uuid4())[:8].upper()


def get_cluster_topic(subject: str, cluster_id) -> str:
    # 1. Convert cluster_id to integer (safe way to handle string inputs)
    try:
        cluster_key = int(cluster_id)
    except ValueError:
        return f"Cluster {cluster_id}"  # Cannot convert to int

    # 2. Ensure subject capitalization matches keys in CLUSTER_TOPICS
    subject_key = subject.capitalize()

    # 3. Perform the lookup using the standardized keys
    if cluster_key in CLUSTER_TOPICS and subject_key in CLUSTER_TOPICS[cluster_key]:
        return CLUSTER_TOPICS[cluster_key][subject_key]

    return f"Cluster {cluster_id}"


def reset_quiz_state(subject: str, total_q: int, mode: str = "normal", weak_only_list: List[int] = None):
    mid = CLUSTER_LIMITS.get(subject, 4) // 2
    start_cluster = mid if mode == "normal" else (weak_only_list[0] if weak_only_list else mid)
    quiz.update({
        "started": True,
        "subject": subject,
        "cluster": start_cluster,
        "question_index": 0,
        "total_questions": total_q,
        "score": 0,
        "used_indices": [],
        "current_question": None,
        "submitted": False,
        "feedback": "",
        "weak_clusters": {} if mode == "normal" else {c: 0 for c in (weak_only_list or [])},
        "mode": mode,
        "weak_only_list": weak_only_list or []
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
            subset = df_subj[df_subj["Cluster"].isin(quiz["weak_only_list"])].drop(quiz["used_indices"],
                                                                                   errors="ignore")
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
            quiz["cluster"] = min(CLUSTER_LIMITS.get(quiz["subject"], quiz["cluster"] + 1), quiz["cluster"] + 1)
        quiz["feedback"] = " Correct! Great job."
    else:
        if quiz["mode"] == "normal":
            quiz["cluster"] = max(MIN_CLUSTER, quiz["cluster"] - 1)
        quiz["feedback"] = f" Wrong! Correct answer: {correct}"
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

# 💡 MODIFIED: Switched to Groq API call and updated model
def get_ai_help(topic: str, subject: str, user_question: str = None, conversation_history: List[Dict] = None):
    """Get AI explanation using Groq's Mixtral 8x7b"""
    if not MCP_AVAILABLE:
        return "AI tutor is not available. Please set up GROQ_API_KEY."

    # --- System Prompt Definition (MUST be here) ---
    system_prompt = f"""You are EDULINE's AI tutor helping a student understand {subject} concepts. 
The student is struggling with: {topic}

Your role:
- Break down complex concepts into simple, easy-to-understand explanations
- Use real-world examples and analogies relevant to a {app.get('area', 'general')} setting
- Be encouraging and patient
- Adapt to high school level understanding
- Keep responses concise (2-3 paragraphs max unless asked for more detail)
- Use clear formatting with bullet points when listing steps or concepts
"""
    # ---------------------------------------------

    if user_question is None:
        user_question = f"Can you explain {topic} in {subject} in a simple way? I'm having trouble understanding it."

    try:
        # Build messages array with conversation history
        # NOTE: system_prompt is correctly used here because it is defined above
        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history if exists
        if conversation_history:
            messages.extend(conversation_history)

        # Add current user question
        messages.append({"role": "user", "content": user_question})

        # Call Groq API
        response = groq_client.chat.completions.create(
            #  NEW FIX APPLIED: Using a current, highly stable Groq model
            model="llama-3.1-8b-instant",
            messages=messages,
            max_tokens=800,
            temperature=0.7,
        )
        return response.choices[0].message.content

    except Exception as e:
        return f"Sorry, I couldn't generate a response: {str(e)}"

# ==============================
# UI: Top header
# ==============================
st.title("🎓 EDULINE")
st.subheader("The Adaptive AI Tutor")

# Sidebar info
if app.get("student_uuid") and app["stage"] != "auth":
    st.sidebar.markdown(f"**Student ID:** {app['student_uuid']}")
    if app.get("name"):
        st.sidebar.markdown(f"**Name:** {app['name']}")
    if app.get("area"):
        st.sidebar.markdown(f"**Area:** {app['area']}")

    if st.sidebar.button(" Show Past Results"):
        try:
            df_results = pd.read_sql_query(
                "SELECT subject, score, total_questions, taken_at FROM results WHERE student_uuid=?",
                conn, params=(app['student_uuid'],))
            if df_results.empty:
                st.sidebar.info("No previous results found.")
            else:
                st.sidebar.dataframe(df_results.sort_values("taken_at", ascending=False).head(10))
        except Exception as e:
            st.sidebar.error(f"Failed to fetch results: {e}")

    if st.sidebar.button(" Logout"):
        app.update({
            "stage": "auth",
            "auth_mode": "login",
            "student_uuid": None,
            "name": "",
            "area": ""
        })
        st.rerun()

# ==============================
# STAGE: Auth (Login/Register)
# ==============================
if app["stage"] == "auth":
    tab1, tab2 = st.tabs([" Login", " Register"])

    with tab1:
        st.markdown("### Welcome back! Login to continue")
        login_id = st.text_input("Student ID", key="login_id", placeholder="EDU-XXXXXXXX")
        login_pass = st.text_input("Password", type="password", key="login_pass")

        if st.button("Login", type="primary", key="login_btn"):
            if not login_id or not login_pass:
                st.error("Please enter both Student ID and password")
            else:
                result = verify_login(conn, login_id, login_pass)
                if result:
                    app["student_uuid"] = result[0]
                    app["name"] = result[1]
                    app["area"] = result[2]
                    st.success(f"Welcome back, {app['name'] or 'Student'}!")
                    app["stage"] = "subject"
                    st.rerun()
                else:
                    st.error("Invalid Student ID or password")

    with tab2:
        st.markdown("### Create your student profile")
        reg_name = st.text_input("Name (optional)", key="reg_name")
        reg_area = st.radio("Where do you live?", ["Urban", "Rural"], key="reg_area")
        reg_pass = st.text_input("Create a password", type="password", key="reg_pass")
        reg_pass_confirm = st.text_input("Confirm password", type="password", key="reg_pass_confirm")

        if st.button("Create Account", type="primary", key="register_btn"):
            if not reg_pass:
                st.error("Please create a password")
            elif reg_pass != reg_pass_confirm:
                st.error("Passwords don't match")
            else:
                student_uuid = gen_uuid()
                try:
                    insert_user(conn, student_uuid, reg_name.strip(), reg_area, reg_pass)
                    app["student_uuid"] = student_uuid
                    app["name"] = reg_name.strip()
                    app["area"] = reg_area
                    st.success(f"✅ Account created! Your Student ID is: **{student_uuid}**")
                    st.info(" Save this ID - you'll need it to login!")
                    app["stage"] = "subject"
                    st.rerun()
                except Exception as e:
                    st.error(f"Registration failed: {e}")

# ==============================
# STAGE: Subject selection
# ==============================
elif app["stage"] == "subject":
    st.markdown(f"#### Welcome{', ' + app['name'] if app.get('name') else ''}! ")
    st.caption(f"ID: **{app['student_uuid']}** | Area: **{app['area']}**")

    # Subject Filtering: Only English, Mathematics, Physics, Chemistry
    allowed_subjects = ["English", "Mathematics", "Physics", "Chemistry"]
    subject = st.selectbox(" Select subject:", options=allowed_subjects)

    total_q = st.slider(" How many questions?", 3, 20, DEFAULT_TOTAL_Q)

    col1, col2 = st.columns(2)
    with col1:
        if st.button(" Start Adaptive Quiz", type="primary"):
            if subject in allowed_subjects:
                reset_quiz_state(subject, total_q, mode="normal")
                app["stage"] = "quiz"
                st.rerun()
            else:
                st.error("Please select a valid subject (English, Mathematics, Physics, or Chemistry).")

    with col2:
        # Check for past quiz results to enable 'Retry Weak Areas'
        has_weak_areas = any(v > 0 for v in quiz.get("weak_clusters", {}).values())

        if st.button(" Retry Weak Areas", disabled=not has_weak_areas):
            weak_list = [c for c, m in quiz["weak_clusters"].items() if m > 0]
            if not weak_list:
                st.info("No recorded weak areas yet. Try a normal quiz first!")
            else:
                # Ensure the selected subject is used, even in weak mode
                reset_quiz_state(subject, total_q, mode="weak_only", weak_only_list=weak_list)
                app["stage"] = "quiz"
                st.rerun()

# ==============================
# STAGE: Quiz
# ==============================
elif app["stage"] == "quiz":
    if not quiz["started"]:
        st.warning("No active quiz. Returning to subject page.")
        app["stage"] = "subject"
        st.rerun()

    st.markdown(f"###  {quiz['subject']}")
    st.caption(
        f"{' Weak Areas Mode' if quiz['mode'] == 'weak_only' else ' Adaptive Mode'} | Student: {app['student_uuid']}")

    if quiz["current_question"] is None:
        ok = load_next_question()
        if not ok:
            st.warning("No more questions available.")
            finish_and_record()
            st.rerun()

    progress_ratio = quiz["question_index"] / quiz["total_questions"]
    st.progress(progress_ratio)
    st.write(f"**Question {quiz['question_index'] + 1}** of {quiz['total_questions']}")

    q = quiz["current_question"]
    topic_name = get_cluster_topic(quiz["subject"], quiz["cluster"])
    st.info(f" **Topic:** {topic_name}")

    st.markdown(f"### {q['Question']}")

    options = {"A": q["Option A"], "B": q["Option B"], "C": q["Option C"], "D": q["Option D"]}
    choice = st.radio("Choose your answer:", options=list(options.keys()),
                      format_func=lambda k: f"{k}. {options[k]}",
                      key=f"choice_{quiz['question_index']}")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button(" Submit", type="primary"):
            submit_answer(choice)
            st.rerun()
    with col2:
        if st.button(" Quit Quiz"):
            finish_and_record()
            st.warning("Quiz ended. Progress saved!")
            st.rerun()
    with col3:
        if st.button(" Restart"):
            quiz.update({
                "started": False,
                "subject": None,
                "cluster": 0,
                "question_index": 0,
                "total_questions": DEFAULT_TOTAL_Q,
                "score": 0,
                "used_indices": [],
                "current_question": None,
                "submitted": False,
                "feedback": "",
                "weak_clusters": {},
                "mode": "normal",
                "weak_only_list": []
            })
            app["stage"] = "subject"
            st.rerun()

    if quiz["submitted"]:
        if "" in quiz["feedback"]:
            st.success(quiz["feedback"])
        else:
            st.error(quiz["feedback"])
            if MCP_AVAILABLE:
                if st.button(" Ask AI Tutor for Help"):
                    chat["active_topic"] = topic_name
                    chat["active_subject"] = quiz["subject"]
                    chat["messages"] = []
                    app["stage"] = "help"
                    st.rerun()

        if st.button(" Next Question", type="primary"):
            quiz["question_index"] += 1
            quiz["current_question"] = None
            quiz["submitted"] = False
            quiz["feedback"] = ""
            if quiz["question_index"] >= quiz["total_questions"]:
                finish_and_record()
            st.rerun()

# ==============================
# STAGE: AI Help Chat
# ==============================
elif app["stage"] == "help":
    st.markdown(f"###  AI Tutor - {chat['active_subject']}")
    st.info(f" Getting help with: **{chat['active_topic']}**")

    # Display chat history
    for msg in chat["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask me anything about this topic...", key="ai_tutor_chat_input"):
        # Add user message
        user_message = {"role": "user", "content": prompt}
        chat["messages"].append(user_message)

        # Display the new user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get AI response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Pass *all* current messages for context, including the latest user message
                response = get_ai_help(
                    chat["active_topic"],
                    chat["active_subject"],
                    user_question=prompt, # The prompt is the user's latest question
                    conversation_history=chat["messages"][:-1] # Pass history *excluding* the latest prompt
                )
                st.markdown(response)
                # Add assistant message to history
                chat["messages"].append({"role": "assistant", "content": response})


        st.rerun()

    # Navigation buttons
    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back to Quiz"):
            app["stage"] = "quiz"
            st.rerun()
    with col2:
        if st.button(" Main Menu"):
            app["stage"] = "subject"
            st.rerun()

# ==============================
# STAGE: Finished
# ==============================
elif app["stage"] == "finished":
    st.balloons()
    st.markdown("##  Quiz Completed!")

    score_pct = (quiz['score'] / quiz['total_questions']) * 100
    st.metric("Final Score", f"{quiz['score']} / {quiz['total_questions']}", f"{score_pct:.0f}%")
    st.progress(1.0)

    if quiz["weak_clusters"]:
        st.markdown("###  Areas for Improvement")
        for cl, misses in sorted(quiz["weak_clusters"].items(), key=lambda x: -x[1]):
            topic = get_cluster_topic(quiz["subject"], cl)
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"- **{topic}**: {misses} mistake(s)")
            with col2:
                if MCP_AVAILABLE and st.button(" Get Help", key=f"help_{cl}"):
                    chat["active_topic"] = topic
                    chat["active_subject"] = quiz["subject"]
                    chat["messages"] = []
                    app["stage"] = "help"
                    st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button(" Practice Weak Areas", type="primary"):
            weak_list = [c for c, m in quiz["weak_clusters"].items() if m > 0]
            if not weak_list:
                st.info("No weak areas to practice!")
            else:
                reset_quiz_state(quiz["subject"], quiz["total_questions"],
                                 mode="weak_only", weak_only_list=weak_list)
                app["stage"] = "quiz"
                st.rerun()

    with col2:
        if st.button(" Choose Another Subject"):
            app["stage"] = "subject"
            st.rerun()