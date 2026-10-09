# app.py
# EDULINE Adaptive Quiz
# - Student accounts + results stored in MySQL (passwords are hashed)
# - AI tutor routes between N-ATLAS (Yoruba / Hausa / Igbo) and Gemini (fallback / English)

import hashlib
import hmac
import json
import os
import random
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import mysql.connector
import pandas as pd
import streamlit as st
from mysql.connector import errorcode, pooling

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# ==============================
# Page config
# ==============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_icon() -> str:
    for name in ("logo_favicon1.png", "logo_faviscon1.png"):
        path = os.path.join(BASE_DIR, name)
        if os.path.exists(path):
            return path
    return "🎓"


st.set_page_config(page_title="EDULINE Adaptive Quiz", page_icon=_find_icon(), layout="centered")

# ==============================
# Constants
# ==============================
QUESTIONS_CSV = os.path.join(BASE_DIR, "cleaned_mcqs_clustered.csv")
REQUIRED_COLS = ["Subject", "Cluster", "Question", "Option A", "Option B", "Option C", "Option D", "Answer"]
DEFAULT_TOTAL_Q = 5
CLUSTER_LIMITS = {"English": 8, "Mathematics": 8, "Physics": 8, "Chemistry": 8}
MIN_CLUSTER = 0
MIN_PASSWORD_LEN = 6
LANGUAGES = ["English", "Yoruba", "Hausa", "Igbo"]
PROVIDER_LABELS = {"natlas": "N-ATLAS", "gemini": "Gemini"}

CLUSTER_TOPICS = {
    0: {"English": "Formal Letters & Vocabulary", "Mathematics": "Algebra (Quadratics & Roots)", "Physics": "Gas Properties", "Chemistry": "Coal & Combustion"},
    1: {"English": "Speech Forms & Simplification", "Mathematics": "Simplification & Expressions", "Physics": "General Concepts", "Chemistry": "Carbon & Oxides"},
    2: {"English": "Synonyms & Vocabulary", "Mathematics": "Terms & Differences", "Physics": "Units & Measurements", "Chemistry": "Acids & Reactions"},
    3: {"English": "Essay Writing & Summary", "Mathematics": "General Concepts", "Physics": "General Concepts", "Chemistry": "Industrial Processes & Raw Materials"},
    4: {"English": "Idioms & Word Choice", "Mathematics": "Sequences (GP) & Terms", "Physics": "Gas Processes", "Chemistry": "General Concepts"},
    5: {"English": "Advanced Vocabulary", "Mathematics": "Algebra (x², 2x) & Variation", "Physics": "Electricity, Sound & Current", "Chemistry": "Salts"},
    6: {"English": "Phrasal Verbs & Word Meanings", "Mathematics": "Logarithms (log₁₀) & Formulas", "Physics": "Heat", "Chemistry": "General Concepts"},
    7: {"English": "Antonyms & Opposites", "Mathematics": "Geometry (Area, Radius, Height)", "Physics": "General Concepts", "Chemistry": "Compounds"},
    8: {"English": "Multiple Choice Vocabulary", "Mathematics": "Probability & Numbers", "Physics": "General Concepts", "Chemistry": "Ions & Trioxocarbonates"},
}


# ==============================
# Secrets / config helper
# ==============================
def get_secret(name: str, default=None):
    """Environment variable first, then Streamlit secrets."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return default


# ==============================
# MySQL
# ==============================
def db_config() -> dict:
    cfg = {
        "host": get_secret("MYSQL_HOST", "localhost"),
        "port": int(get_secret("MYSQL_PORT", 3306)),
        "user": get_secret("MYSQL_USER"),
        "password": get_secret("MYSQL_PASSWORD"),
        "database": get_secret("MYSQL_DATABASE", "eduline"),
        "charset": "utf8mb4",
        "connection_timeout": 10,
    }
    ssl_ca = get_secret("MYSQL_SSL_CA")
    if ssl_ca:
        cfg["ssl_ca"] = ssl_ca
    return cfg


@st.cache_resource(show_spinner=False)
def get_pool():
    return pooling.MySQLConnectionPool(
        pool_name="eduline_pool", pool_size=5, pool_reset_session=True, **db_config()
    )


@contextmanager
def db_cursor(commit: bool = False, dictionary: bool = False):
    """Borrow a pooled connection, yield a cursor, always hand the connection back."""
    conn = get_pool().get_connection()
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)  # survive idle-timeout drops
        cur = conn.cursor(dictionary=dictionary)
        try:
            yield cur
            if commit:
                conn.commit()
        finally:
            cur.close()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()  # returns it to the pool


USERS_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_uuid VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(100),
    area VARCHAR(10),
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL
) CHARACTER SET utf8mb4
"""

RESULTS_DDL = """
CREATE TABLE IF NOT EXISTS results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_uuid VARCHAR(20) NOT NULL,
    subject VARCHAR(50),
    score INT,
    total_questions INT,
    progress DOUBLE,
    weak_clusters_json TEXT,
    taken_at DATETIME NOT NULL,
    INDEX idx_results_student (student_uuid, subject, taken_at)
) CHARACTER SET utf8mb4
"""


@st.cache_resource(show_spinner=False)
def init_db() -> bool:
    with db_cursor(commit=True) as cur:
        cur.execute(USERS_DDL)
        cur.execute(RESULTS_DDL)
    return True


# ---- password hashing (PBKDF2-SHA256, standard library only) ----
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ---- users ----
def gen_uuid() -> str:
    return "EDU-" + uuid.uuid4().hex[:8].upper()


def create_user(name: str, area: str, password: str) -> str:
    pw_hash = hash_password(password)
    for _ in range(5):
        student_uuid = gen_uuid()
        try:
            with db_cursor(commit=True) as cur:
                cur.execute(
                    "INSERT INTO users (student_uuid, name, area, password_hash, created_at) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (student_uuid, name, area, pw_hash, datetime.now()),
                )
            return student_uuid
        except mysql.connector.IntegrityError as e:
            if e.errno != errorcode.ER_DUP_ENTRY:
                raise  # not an ID collision; real error
    raise RuntimeError("Could not generate a unique Student ID. Please try again.")


def verify_login(student_uuid: str, password: str) -> Optional[dict]:
    with db_cursor(dictionary=True) as cur:
        cur.execute(
            "SELECT student_uuid, name, area, password_hash FROM users WHERE student_uuid = %s",
            (student_uuid,),
        )
        row = cur.fetchone()
    if row and check_password(password, row["password_hash"]):
        return row
    return None


# ---- results ----
def save_result(student_uuid: str, subject: str, score: int, total: int, progress: float, weak: dict):
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO results (student_uuid, subject, score, total_questions, progress, "
            "weak_clusters_json, taken_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (student_uuid, subject, score, total, progress, json.dumps(weak), datetime.now()),
        )


def get_results_df(student_uuid: str, limit: int = 10) -> pd.DataFrame:
    with db_cursor(dictionary=True) as cur:
        cur.execute(
            "SELECT subject, score, total_questions, taken_at FROM results "
            "WHERE student_uuid = %s ORDER BY taken_at DESC LIMIT %s",
            (student_uuid, limit),
        )
        rows = cur.fetchall()
    return pd.DataFrame(rows)


def get_weak_clusters(student_uuid: str, subject: str, last_n: int = 10) -> List[Tuple[int, int]]:
    """Clusters the student missed most in their last N quizzes of this subject: [(cluster, misses)]."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT weak_clusters_json FROM results WHERE student_uuid = %s AND subject = %s "
            "ORDER BY taken_at DESC LIMIT %s",
            (student_uuid, subject, last_n),
        )
        rows = cur.fetchall()
    totals: Dict[int, int] = {}
    for (raw,) in rows:
        try:
            data = json.loads(raw or "{}")
        except ValueError:
            continue
        for cluster, misses in data.items():
            if misses and misses > 0:
                totals[int(cluster)] = totals.get(int(cluster), 0) + int(misses)
    return sorted(totals.items(), key=lambda kv: -kv[1])


# Connect + create tables once per server process
try:
    if not get_secret("MYSQL_USER"):
        raise RuntimeError("MYSQL_USER is not set. Add your MySQL settings to .env or Streamlit secrets.")
    init_db()
except Exception as e:
    st.error(f"Could not connect to the MySQL database: {e}")
    st.stop()


# ==============================
# Questions
# ==============================
@st.cache_data
def load_questions(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Questions CSV is missing columns: {missing}")
    df = df.dropna(subset=["Subject", "Cluster"])
    df = df[df["Subject"] != "Subject"]  # stray header rows
    df["Cluster"] = df["Cluster"].astype(float).astype(int)
    return df.reset_index(drop=True)


try:
    df_all = load_questions(QUESTIONS_CSV)
except Exception as e:
    st.error(f"Could not load questions: {e}")
    st.stop()

# ==============================
# AI tutor providers
# ==============================
@st.cache_resource(show_spinner=False)
def get_gemini_client():
    key = get_secret("GOOGLE_API_KEY")
    if not key:
        return None
    try:
        from google import genai

        return genai.Client(api_key=key)
    except Exception:
        return None


@st.cache_resource(show_spinner=False)
def get_natlas_client():
    base_url = get_secret("NATLAS_BASE_URL")
    if not base_url:
        return None
    try:
        from openai import OpenAI

        return OpenAI(
            base_url=base_url,
            api_key=get_secret("NATLAS_API_KEY", "not-needed"),
            timeout=90,
            max_retries=1,
        )
    except Exception:
        return None


NATLAS_MODEL = get_secret("NATLAS_MODEL", "NCAIR1/N-ATLaS")
GEMINI_MODELS = [m.strip() for m in str(get_secret("GEMINI_MODELS", "gemini-2.5-flash,gemini-2.0-flash")).split(",") if m.strip()]
PROVIDER_AVAILABLE = {
    "natlas": get_natlas_client() is not None,
    "gemini": get_gemini_client() is not None,
}
AI_AVAILABLE = any(PROVIDER_AVAILABLE.values())


def provider_order(language: str) -> List[str]:
    """Local languages try N-ATLAS first; English tries Gemini first. Each is the other's fallback."""
    order = ["natlas", "gemini"] if language != "English" else ["gemini", "natlas"]
    return [p for p in order if PROVIDER_AVAILABLE[p]]


def build_system_prompt(topic: str, subject: str, language: str, area: str, context: Optional[dict]) -> str:
    prompt = (
        f"You are EDULINE's AI tutor helping a Nigerian secondary-school student with {subject}.\n"
        f"The student is struggling with: {topic}.\n\n"
        "Instructions:\n"
        "- Explain step by step, starting with a simple definition.\n"
        "- Break complex ideas into small parts and include a worked example when useful.\n"
        f"- Use everyday examples that fit a {area or 'general'} setting.\n"
        "- Explain any formula or calculation involved.\n"
        "- End with a short summary. Adapt depth to the student's question.\n"
    )
    if language != "English":
        prompt += f"- Reply in {language}. Keep key technical terms in English in brackets.\n"
    if context:
        opts = "\n".join(f"  {k}. {v}" for k, v in context["options"].items())
        prompt += (
            "\nThe student just answered this quiz question:\n"
            f"Question: {context['question']}\n{opts}\n"
            f"Student chose: {context.get('chosen')}. Correct answer: {context['correct']}.\n"
        )
    return prompt


def call_natlas(system_prompt: str, history: List[dict], question: str) -> str:
    client = get_natlas_client()
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": question}]
    resp = client.chat.completions.create(
        model=NATLAS_MODEL, messages=messages, max_tokens=900, temperature=0.7
    )
    return resp.choices[0].message.content


def call_gemini(system_prompt: str, history: List[dict], question: str) -> str:
    from google.genai import types

    client = get_gemini_client()
    contents = [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in history + [{"role": "user", "content": question}]
    ]
    config = types.GenerateContentConfig(
        system_instruction=system_prompt, max_output_tokens=1500, temperature=0.7
    )
    last_error = None
    for model in GEMINI_MODELS:
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            return resp.text
        except Exception as e:
            last_error = e
            if "503" in str(e) or "UNAVAILABLE" in str(e) or "404" in str(e):
                continue  # busy or model not available: try the next one
            raise
    raise RuntimeError(f"All Gemini models failed: {last_error}")


def get_ai_help(topic, subject, question, history, language, area, context) -> Tuple[str, Optional[str]]:
    """Returns (answer, provider_label). Tries providers in order, falling back on any failure."""
    system_prompt = build_system_prompt(topic, subject, language, area, context)
    trimmed = [{"role": m["role"], "content": m["content"]} for m in history][-10:]
    for provider in provider_order(language):
        try:
            if provider == "natlas":
                text = call_natlas(system_prompt, trimmed, question)
            else:
                text = call_gemini(system_prompt, trimmed, question)
            if text and text.strip():
                return text.strip(), PROVIDER_LABELS[provider]
        except Exception as e:
            print(f"[AI tutor] {provider} failed: {e}")
    return "⚠️ The AI tutor couldn't answer right now. Please try again in a moment.", None


# ==============================
# Session state
# ==============================
def default_app() -> dict:
    return {"stage": "auth", "student_uuid": None, "name": "", "area": ""}


def default_quiz() -> dict:
    return {
        "started": False, "run_id": "", "subject": None, "cluster": 0, "question_index": 0,
        "total_questions": DEFAULT_TOTAL_Q, "score": 0, "answered": 0, "used_indices": [],
        "current_question": None, "submitted": False, "last_correct": False, "last_choice": None,
        "feedback": "", "weak_clusters": {}, "mode": "normal", "weak_only_list": [], "save_error": "",
    }


def default_chat() -> dict:
    return {"messages": [], "active_topic": None, "active_subject": None, "context": None, "return_to": "quiz"}


for key, factory in (("app", default_app), ("quiz", default_quiz), ("chat", default_chat)):
    if key not in st.session_state:
        st.session_state[key] = factory()

app = st.session_state.app
quiz = st.session_state.quiz
chat = st.session_state.chat


def reset_session():
    """Logout: wipe everything so the next student on this device starts clean."""
    for d, factory in ((app, default_app), (quiz, default_quiz), (chat, default_chat)):
        d.clear()
        d.update(factory())


# ==============================
# Quiz logic
# ==============================
def get_cluster_topic(subject: str, cluster_id: int) -> str:
    return CLUSTER_TOPICS.get(cluster_id, {}).get(subject, f"Cluster {cluster_id}")


def normalize_answer(raw) -> str:
    text = str(raw).strip().upper()
    if text[:1] in "ABCD" and (len(text) == 1 or text[1] in ".) "):
        return text[:1]
    return text


def reset_quiz_state(subject: str, total_q: int, mode: str = "normal", weak_only_list: Optional[List[int]] = None):
    mid = CLUSTER_LIMITS.get(subject, 8) // 2
    weak_only_list = weak_only_list or []
    start_cluster = mid if mode == "normal" or not weak_only_list else weak_only_list[0]
    quiz.update(default_quiz())
    quiz.update({
        "started": True, "run_id": uuid.uuid4().hex[:6], "subject": subject, "cluster": start_cluster,
        "total_questions": total_q, "mode": mode, "weak_only_list": weak_only_list,
        "weak_clusters": {} if mode == "normal" else {c: 0 for c in weak_only_list},
    })


def load_next_question() -> bool:
    df_subj = df_all[df_all["Subject"] == quiz["subject"]]
    used = quiz["used_indices"]

    if quiz["mode"] == "weak_only" and quiz["weak_only_list"]:
        target = random.choice(quiz["weak_only_list"])
    else:
        target = quiz["cluster"]
    quiz["cluster"] = target

    subset = df_subj[df_subj["Cluster"] == target].drop(used, errors="ignore")
    if subset.empty:
        if quiz["mode"] == "weak_only" and quiz["weak_only_list"]:
            subset = df_subj[df_subj["Cluster"].isin(quiz["weak_only_list"])].drop(used, errors="ignore")
        else:
            subset = df_subj.drop(used, errors="ignore")
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
    correct = normalize_answer(q["Answer"])
    q_cluster = int(q["Cluster"])  # the question's own topic, not the adaptive pointer
    quiz["answered"] += 1
    quiz["last_choice"] = choice_key

    if choice_key == correct:
        quiz["score"] += 1
        quiz["last_correct"] = True
        if quiz["mode"] == "normal":
            quiz["cluster"] = min(CLUSTER_LIMITS.get(quiz["subject"], 8), quiz["cluster"] + 1)
        quiz["feedback"] = "✅ Correct! Great job."
    else:
        quiz["last_correct"] = False
        if quiz["mode"] == "normal":
            quiz["cluster"] = max(MIN_CLUSTER, quiz["cluster"] - 1)
        answer_text = q.get(f"Option {correct}", "")
        answer_text = "" if pd.isna(answer_text) else str(answer_text)
        quiz["feedback"] = f"❌ Wrong! Correct answer: {correct}. {answer_text}".strip()
        quiz["weak_clusters"][q_cluster] = quiz["weak_clusters"].get(q_cluster, 0) + 1
    quiz["submitted"] = True


def finish_and_record():
    if quiz["answered"] > 0:
        try:
            progress = quiz["answered"] / max(1, quiz["total_questions"])
            save_result(app["student_uuid"], quiz["subject"], quiz["score"], quiz["answered"],
                        progress, quiz["weak_clusters"])
        except Exception as e:
            quiz["save_error"] = f"Could not save your result: {e}"
    quiz["started"] = False
    app["stage"] = "finished" if quiz["answered"] > 0 else "subject"


def open_tutor(topic: str, subject: str, context: Optional[dict], return_to: str):
    chat.update({
        "active_topic": topic, "active_subject": subject, "messages": [],
        "context": context, "return_to": return_to,
    })
    app["stage"] = "help"


# ==============================
# Header + sidebar
# ==============================
st.title("🎓 EDULINE")
st.caption("Adaptive quizzes with an AI tutor")

if app["student_uuid"] and app["stage"] != "auth":
    st.sidebar.markdown(f"**Student ID:** `{app['student_uuid']}`")
    if app.get("name"):
        st.sidebar.markdown(f"**Name:** {app['name']}")
    if app.get("area"):
        st.sidebar.markdown(f"**Area:** {app['area']}")

    if st.sidebar.checkbox("📊 Show past results"):
        try:
            df_results = get_results_df(app["student_uuid"])
            if df_results.empty:
                st.sidebar.info("No previous results yet.")
            else:
                st.sidebar.dataframe(df_results, hide_index=True)
        except Exception as e:
            st.sidebar.error(f"Failed to fetch results: {e}")

    if st.sidebar.button("🚪 Logout"):
        reset_session()
        st.rerun()

# ==============================
# STAGE: Auth
# ==============================
if app["stage"] == "auth":
    tab_login, tab_register = st.tabs(["🔐 Login", "✨ Register"])

    with tab_login:
        st.markdown("### Welcome back!")
        with st.form("login_form"):
            login_id = st.text_input("Student ID", placeholder="EDU-XXXXXXXX")
            login_pass = st.text_input("Password", type="password")
            login_clicked = st.form_submit_button("Login", type="primary")
        if login_clicked:
            sid = login_id.strip().upper()
            if not sid or not login_pass:
                st.error("Please enter both your Student ID and password.")
            else:
                user, db_error = None, None
                try:
                    user = verify_login(sid, login_pass)
                except Exception as e:
                    db_error = e
                if db_error:
                    st.error(f"Could not reach the database: {db_error}")
                elif user:
                    app.update({
                        "student_uuid": user["student_uuid"], "name": user["name"] or "",
                        "area": user["area"] or "", "stage": "subject",
                    })
                    st.rerun()
                else:
                    st.error("Invalid Student ID or password.")

    with tab_register:
        st.markdown("### Create your student profile")
        with st.form("register_form"):
            reg_name = st.text_input("Name (optional)")
            reg_area = st.radio("Where do you live?", ["Urban", "Rural"], horizontal=True)
            reg_pass = st.text_input("Create a password", type="password",
                                     help=f"At least {MIN_PASSWORD_LEN} characters")
            reg_pass2 = st.text_input("Confirm password", type="password")
            reg_clicked = st.form_submit_button("Create Account", type="primary")
        if reg_clicked:
            if len(reg_pass) < MIN_PASSWORD_LEN:
                st.error(f"Password must be at least {MIN_PASSWORD_LEN} characters.")
            elif reg_pass != reg_pass2:
                st.error("Passwords don't match.")
            else:
                new_id, db_error = None, None
                try:
                    new_id = create_user(reg_name.strip(), reg_area, reg_pass)
                except Exception as e:
                    db_error = e
                if db_error:
                    st.error(f"Registration failed: {db_error}")
                else:
                    app.update({"student_uuid": new_id, "name": reg_name.strip(),
                                "area": reg_area, "stage": "registered"})
                    st.rerun()

# ==============================
# STAGE: Registered (show the Student ID before moving on)
# ==============================
elif app["stage"] == "registered":
    st.success("🎉 Account created!")
    st.markdown("### Your Student ID")
    st.code(app["student_uuid"], language=None)
    st.warning("Write this ID down. You need it, plus your password, to log in next time.")
    if st.button("Continue", type="primary"):
        app["stage"] = "subject"
        st.rerun()

# ==============================
# STAGE: Subject selection
# ==============================
elif app["stage"] == "subject":
    st.markdown(f"#### Welcome{', ' + app['name'] if app.get('name') else ''}! 👋")
    st.caption(f"ID: **{app['student_uuid']}** | Area: **{app['area']}**")

    available = set(df_all["Subject"].unique())
    subjects = [s for s in CLUSTER_LIMITS if s in available] or sorted(available)
    subject = st.selectbox("Select subject:", subjects)
    total_q = st.slider("How many questions?", 3, 20, DEFAULT_TOTAL_Q)

    try:
        weak_history = get_weak_clusters(app["student_uuid"], subject)
    except Exception:
        weak_history = []

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Start Adaptive Quiz", type="primary"):
            reset_quiz_state(subject, total_q, mode="normal")
            app["stage"] = "quiz"
            st.rerun()
    with col2:
        if st.button("🎯 Retry Weak Areas", disabled=not weak_history):
            reset_quiz_state(subject, total_q, mode="weak_only",
                             weak_only_list=[c for c, _ in weak_history])
            app["stage"] = "quiz"
            st.rerun()

    if weak_history:
        topics = ", ".join(get_cluster_topic(subject, c) for c, _ in weak_history[:4])
        st.caption(f"Your weak areas in {subject}: {topics}")
    else:
        st.caption("Finish a quiz and your weak areas will show up here.")

# ==============================
# STAGE: Quiz
# ==============================
elif app["stage"] == "quiz":
    if not quiz["started"]:
        app["stage"] = "subject"
        st.rerun()

    if quiz["current_question"] is None:
        if not load_next_question():
            finish_and_record()
            st.rerun()

    q = quiz["current_question"]
    topic_name = get_cluster_topic(quiz["subject"], int(q["Cluster"]))

    st.markdown(f"### 📘 {quiz['subject']}")
    st.caption(f"{'🎯 Weak Areas Mode' if quiz['mode'] == 'weak_only' else '🚀 Adaptive Mode'}")
    st.progress(min(1.0, quiz["question_index"] / max(1, quiz["total_questions"])))
    st.write(f"**Question {quiz['question_index'] + 1}** of {quiz['total_questions']}")
    st.info(f"📌 **Topic:** {topic_name}")
    st.markdown(f"### {q['Question']}")

    options = {"A": q["Option A"], "B": q["Option B"], "C": q["Option C"], "D": q["Option D"]}
    choice = st.radio(
        "Choose your answer:", list(options.keys()), index=None,
        format_func=lambda k: f"{k}. {options[k]}",
        key=f"choice_{quiz['run_id']}_{quiz['question_index']}",
        disabled=quiz["submitted"],
    )

    col1, col2 = st.columns(2)
    with col1:
        if not quiz["submitted"]:
            if st.button("✅ Submit", type="primary"):
                if choice is None:
                    st.warning("Pick an answer first.")
                else:
                    submit_answer(choice)
                    st.rerun()
        else:
            is_last = quiz["question_index"] + 1 >= quiz["total_questions"]
            if st.button("🏁 See Results" if is_last else "➡️ Next Question", type="primary"):
                quiz["question_index"] += 1
                quiz["current_question"] = None
                quiz["submitted"] = False
                quiz["feedback"] = ""
                if is_last:
                    finish_and_record()
                st.rerun()
    with col2:
        if st.button("🚪 Quit Quiz"):
            finish_and_record()
            st.rerun()

    if quiz["submitted"]:
        if quiz["last_correct"]:
            st.success(quiz["feedback"])
        else:
            st.error(quiz["feedback"])
            if AI_AVAILABLE and st.button("🤖 Ask AI Tutor for Help"):
                open_tutor(
                    topic_name, quiz["subject"],
                    {"question": q["Question"], "options": options,
                     "correct": normalize_answer(q["Answer"]), "chosen": quiz["last_choice"]},
                    return_to="quiz",
                )
                st.rerun()

# ==============================
# STAGE: AI Help
# ==============================
elif app["stage"] == "help":
    st.markdown(f"### 🤖 AI Tutor - {chat['active_subject']}")
    st.info(f"📌 Getting help with: **{chat['active_topic']}**")

    language = st.selectbox("Explain in:", LANGUAGES, key="tutor_language")
    if language != "English" and not PROVIDER_AVAILABLE["natlas"]:
        st.caption("N-ATLAS isn't configured, so local-language answers will come from Gemini.")

    for m in chat["messages"]:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m.get("provider"):
                st.caption(f"Answered by {m['provider']}")

    pending = None
    if chat["context"] and not chat["messages"]:
        if st.button("💡 Explain this question to me"):
            pending = "Please explain why the correct answer is right and where my answer went wrong."

    prompt = st.chat_input("Ask me anything about this topic...") or pending
    if prompt:
        history = list(chat["messages"])
        chat["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                reply, provider = get_ai_help(
                    chat["active_topic"], chat["active_subject"], prompt, history,
                    language, app.get("area"), chat["context"],
                )
        chat["messages"].append({"role": "assistant", "content": reply, "provider": provider})
        st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("← Back"):
            app["stage"] = chat["return_to"] if chat["return_to"] == "finished" or quiz["started"] else "subject"
            st.rerun()
    with col2:
        if st.button("🏠 Main Menu"):
            app["stage"] = "subject"
            st.rerun()

# ==============================
# STAGE: Finished
# ==============================
elif app["stage"] == "finished":
    st.balloons()
    st.markdown("## 🎉 Quiz Completed!")
    if quiz["save_error"]:
        st.warning(quiz["save_error"])

    answered = max(1, quiz["answered"])
    st.metric("Final Score", f"{quiz['score']} / {quiz['answered']}", f"{quiz['score'] / answered * 100:.0f}%")
    st.progress(1.0)

    weak_now = {c: m for c, m in quiz["weak_clusters"].items() if m > 0}
    if weak_now:
        st.markdown("### 📊 Areas for Improvement")
        for cl, misses in sorted(weak_now.items(), key=lambda kv: -kv[1]):
            topic = get_cluster_topic(quiz["subject"], cl)
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"- **{topic}**: {misses} mistake(s)")
            with c2:
                if AI_AVAILABLE and st.button("🤖 Get Help", key=f"help_{cl}"):
                    open_tutor(topic, quiz["subject"], None, return_to="finished")
                    st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🎯 Practice Weak Areas", type="primary", disabled=not weak_now):
            reset_quiz_state(quiz["subject"], quiz["total_questions"],
                             mode="weak_only", weak_only_list=list(weak_now.keys()))
            app["stage"] = "quiz"
            st.rerun()
    with col2:
        if st.button("📚 Choose Another Subject"):
            app["stage"] = "subject"
            st.rerun()
