import React, { useState, useEffect, useMemo } from "react";
import { 
  BookOpen, 
  Brain, 
  CheckCircle2, 
  ChevronRight, 
  History, 
  LogOut, 
  MessageSquare, 
  Play, 
  RotateCcw, 
  Trophy, 
  User as UserIcon,
  XCircle,
  AlertCircle,
  Loader2
} from "lucide-react";
import { motion, AnimatePresence } from "motion/react";
import { GoogleGenAI } from "@google/genai";
import { cn } from "@/src/lib/utils";
import { 
  User, 
  Question, 
  QuizState, 
  ChatState, 
  CLUSTER_TOPICS, 
  CLUSTER_LIMITS,
  ChatMessage
} from "./types";

// --- API Service ---
const API_BASE = "/api";

const api = {
  register: async (data: any) => {
    const res = await fetch(`${API_BASE}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },
  login: async (data: any) => {
    const res = await fetch(`${API_BASE}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },
  getQuestions: async (subject: string): Promise<Question[]> => {
    const res = await fetch(`${API_BASE}/questions?subject=${subject}`);
    return res.json();
  },
  saveResults: async (data: any) => {
    const res = await fetch(`${API_BASE}/results`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    return res.json();
  },
};

// --- Gemini Service ---
const genAI = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || "" });

async function getAiHelp(topic: string, subject: string, userQuestion: string, history: ChatMessage[], area: string) {
  const model = genAI.models.get({ model: "gemini-3-flash-preview" });
  
  const systemInstruction = `You are EDULINE's AI tutor helping a student understand ${subject}. 
    The student is struggling with: ${topic}.
    - Break down concepts into simple explanations.
    - Use real-world examples relevant to a ${area} setting.
    - Keep responses concise (2-3 paragraphs max).`;

  const contents = [
    { role: "user", parts: [{ text: systemInstruction }] },
    ...history.map(msg => ({
      role: msg.role === "assistant" ? "model" : "user",
      parts: [{ text: msg.content }]
    })),
    { role: "user", parts: [{ text: userQuestion }] }
  ];

  const result = await genAI.models.generateContent({
    model: "gemini-3-flash-preview",
    contents,
  });

  return result.text || "Sorry, I couldn't generate a response.";
}

// --- Main App Component ---
export default function App() {
  const [stage, setStage] = useState<"auth" | "subject" | "quiz" | "help" | "finished">("auth");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [user, setUser] = useState<User | null>(null);
  const [allQuestions, setAllQuestions] = useState<Question[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [quiz, setQuiz] = useState<QuizState>({
    started: false,
    subject: null,
    cluster: 0,
    questionIndex: 0,
    totalQuestions: 5,
    score: 0,
    usedIndices: [],
    currentQuestion: null,
    submitted: false,
    feedback: "",
    weakClusters: {},
    mode: "normal",
    weakOnlyList: [],
  });

  const [chat, setChat] = useState<ChatState>({
    messages: [],
    activeTopic: null,
    activeSubject: null,
  });

  // --- Auth Handlers ---
  const handleLogin = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const formData = new FormData(e.currentTarget);
    const student_uuid = formData.get("student_uuid") as string;
    const password = formData.get("password") as string;

    try {
      const res = await api.login({ student_uuid, password });
      if (res.success) {
        setUser(res.user);
        setStage("subject");
      } else {
        setError(res.error || "Login failed");
      }
    } catch (err) {
      setError("An error occurred during login");
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const formData = new FormData(e.currentTarget);
    const name = formData.get("name") as string;
    const area = formData.get("area") as string;
    const password = formData.get("password") as string;
    const confirm = formData.get("confirm") as string;

    if (password !== confirm) {
      setError("Passwords do not match");
      setLoading(false);
      return;
    }

    const student_uuid = "EDU-" + Math.random().toString(36).substring(2, 10).toUpperCase();

    try {
      const res = await api.register({ student_uuid, name, area, password });
      if (res.success) {
        setUser({ student_uuid, name, area });
        setStage("subject");
      } else {
        setError(res.error || "Registration failed");
      }
    } catch (err) {
      setError("An error occurred during registration");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setUser(null);
    setStage("auth");
    setQuiz({ ...quiz, started: false });
  };

  // --- Quiz Handlers ---
  const startQuiz = async (subject: string, totalQ: number, mode: "normal" | "weak_only" = "normal", weakOnlyList: number[] = []) => {
    setLoading(true);
    try {
      const questions = await api.getQuestions(subject);
      setAllQuestions(questions);
      
      const mid = Math.floor((CLUSTER_LIMITS[subject] || 4) / 2);
      const startCluster = mode === "normal" ? mid : (weakOnlyList[0] ?? mid);
      
      const initialQuiz: QuizState = {
        started: true,
        subject,
        cluster: startCluster,
        questionIndex: 0,
        totalQuestions: totalQ,
        score: 0,
        usedIndices: [],
        currentQuestion: null,
        submitted: false,
        feedback: "",
        weakClusters: mode === "normal" ? {} : weakOnlyList.reduce((acc, c) => ({ ...acc, [c]: 0 }), {}),
        mode,
        weakOnlyList,
      };

      setQuiz(initialQuiz);
      setStage("quiz");
      loadNextQuestion(initialQuiz, questions);
    } catch (err) {
      setError("Failed to load questions");
    } finally {
      setLoading(false);
    }
  };

  const loadNextQuestion = (currentState: QuizState, questionsSource: Question[]) => {
    const filtered = questionsSource.filter(q => q.Subject === currentState.subject);
    let targetCluster = currentState.cluster;

    if (currentState.mode === "weak_only" && currentState.weakOnlyList.length > 0) {
      if (!currentState.weakOnlyList.includes(targetCluster)) {
        targetCluster = currentState.weakOnlyList[Math.floor(Math.random() * currentState.weakOnlyList.length)];
      }
    }

    let subset = filtered.filter((q, idx) => 
      Number(q.Cluster) === targetCluster && !currentState.usedIndices.includes(idx)
    );

    if (subset.length === 0) {
      if (currentState.mode === "weak_only") {
        subset = filtered.filter((q, idx) => 
          currentState.weakOnlyList.includes(Number(q.Cluster)) && !currentState.usedIndices.includes(idx)
        );
      } else {
        subset = filtered.filter((q, idx) => !currentState.usedIndices.includes(idx));
      }
    }

    if (subset.length === 0) {
      finishQuiz(currentState);
      return;
    }

    const randomIndex = Math.floor(Math.random() * subset.length);
    const q = subset[randomIndex];
    const originalIndex = filtered.indexOf(q);

    setQuiz(prev => ({
      ...prev,
      cluster: targetCluster,
      currentQuestion: q,
      usedIndices: [...prev.usedIndices, originalIndex],
      submitted: false,
      feedback: "",
    }));
  };

  const handleSubmitAnswer = (choice: string) => {
    if (!quiz.currentQuestion) return;
    
    const correct = quiz.currentQuestion.Answer.trim().toUpperCase();
    const isCorrect = choice === correct;
    
    let nextCluster = quiz.cluster;
    const newWeakClusters = { ...quiz.weakClusters };

    if (isCorrect) {
      if (quiz.mode === "normal") {
        nextCluster = Math.min(CLUSTER_LIMITS[quiz.subject!] || 8, quiz.cluster + 1);
      }
    } else {
      if (quiz.mode === "normal") {
        nextCluster = Math.max(0, quiz.cluster - 1);
      }
      newWeakClusters[quiz.cluster] = (newWeakClusters[quiz.cluster] || 0) + 1;
    }

    setQuiz(prev => ({
      ...prev,
      score: isCorrect ? prev.score + 1 : prev.score,
      cluster: nextCluster,
      weakClusters: newWeakClusters,
      submitted: true,
      feedback: isCorrect ? "✅ Correct! Great job." : `❌ Wrong! Correct answer: ${correct}`,
    }));
  };

  const finishQuiz = async (currentState: QuizState) => {
    const progress = currentState.questionIndex / currentState.totalQuestions;
    try {
      await api.saveResults({
        student_uuid: user?.student_uuid,
        subject: currentState.subject,
        score: currentState.score,
        total_questions: currentState.totalQuestions,
        progress,
        weak_clusters: currentState.weakClusters,
      });
    } catch (err) {
      console.error("Failed to save results", err);
    }
    setStage("finished");
  };

  // --- Chat Handlers ---
  const handleAskAI = async (topic: string, subject: string) => {
    setChat({
      messages: [],
      activeTopic: topic,
      activeSubject: subject,
    });
    setStage("help");
  };

  const sendMessage = async (text: string) => {
    if (!text.trim()) return;
    
    const newUserMsg: ChatMessage = { role: "user", content: text };
    const updatedMessages = [...chat.messages, newUserMsg];
    setChat(prev => ({ ...prev, messages: updatedMessages }));

    try {
      const response = await getAiHelp(
        chat.activeTopic!,
        chat.activeSubject!,
        text,
        chat.messages,
        user?.area || "general"
      );
      setChat(prev => ({
        ...prev,
        messages: [...prev.messages, newUserMsg, { role: "assistant", content: response }]
      }));
    } catch (err) {
      setChat(prev => ({
        ...prev,
        messages: [...prev.messages, newUserMsg, { role: "assistant", content: "Error connecting to AI Tutor." }]
      }));
    }
  };

  // --- Render Helpers ---
  const getTopicName = (subject: string, cluster: number) => {
    return CLUSTER_TOPICS[cluster]?.[subject] || `Cluster ${cluster}`;
  };

  return (
    <div className="min-h-screen bg-[#F5F5F0] text-[#141414] font-sans selection:bg-[#5A5A40] selection:text-white">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-[#141414]/10 px-6 py-4 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="w-10 h-10 bg-[#5A5A40] rounded-xl flex items-center justify-center text-white">
            <BookOpen size={24} />
          </div>
          <h1 className="text-xl font-bold tracking-tight">EDULINE</h1>
        </div>
        {user && (
          <div className="flex items-center gap-4">
            <div className="hidden md:block text-right">
              <p className="text-sm font-medium">{user.name || "Student"}</p>
              <p className="text-[10px] text-[#141414]/50 uppercase tracking-wider">{user.student_uuid}</p>
            </div>
            <button 
              onClick={handleLogout}
              className="p-2 hover:bg-red-50 text-red-600 rounded-full transition-colors"
              title="Logout"
            >
              <LogOut size={20} />
            </button>
          </div>
        )}
      </header>

      <main className="max-w-2xl mx-auto px-6 py-12">
        <AnimatePresence mode="wait">
          {/* --- Auth Stage --- */}
          {stage === "auth" && (
            <motion.div 
              key="auth"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="bg-white p-8 rounded-[32px] shadow-xl shadow-black/5"
            >
              <div className="flex gap-4 mb-8 p-1 bg-[#F5F5F0] rounded-2xl">
                <button 
                  onClick={() => setAuthMode("login")}
                  className={cn(
                    "flex-1 py-3 rounded-xl text-sm font-medium transition-all",
                    authMode === "login" ? "bg-white shadow-sm text-[#141414]" : "text-[#141414]/50 hover:text-[#141414]"
                  )}
                >
                  Login
                </button>
                <button 
                  onClick={() => setAuthMode("register")}
                  className={cn(
                    "flex-1 py-3 rounded-xl text-sm font-medium transition-all",
                    authMode === "register" ? "bg-white shadow-sm text-[#141414]" : "text-[#141414]/50 hover:text-[#141414]"
                  )}
                >
                  Register
                </button>
              </div>

              {error && (
                <div className="mb-6 p-4 bg-red-50 text-red-600 rounded-2xl flex items-center gap-3 text-sm">
                  <AlertCircle size={18} />
                  {error}
                </div>
              )}

              {authMode === "login" ? (
                <form onSubmit={handleLogin} className="space-y-4">
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-2 ml-1">Student ID</label>
                    <input 
                      name="student_uuid"
                      required
                      placeholder="EDU-XXXXXXXX"
                      className="w-full px-5 py-4 bg-[#F5F5F0] rounded-2xl border-2 border-transparent focus:border-[#5A5A40] outline-none transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-2 ml-1">Password</label>
                    <input 
                      name="password"
                      type="password"
                      required
                      className="w-full px-5 py-4 bg-[#F5F5F0] rounded-2xl border-2 border-transparent focus:border-[#5A5A40] outline-none transition-all"
                    />
                  </div>
                  <button 
                    disabled={loading}
                    className="w-full py-4 bg-[#5A5A40] text-white rounded-2xl font-bold mt-4 hover:bg-[#4A4A30] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="animate-spin" size={20} /> : "Sign In"}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleRegister} className="space-y-4">
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-2 ml-1">Full Name</label>
                    <input 
                      name="name"
                      placeholder="Optional"
                      className="w-full px-5 py-4 bg-[#F5F5F0] rounded-2xl border-2 border-transparent focus:border-[#5A5A40] outline-none transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-2 ml-1">Area Type</label>
                    <div className="flex gap-4">
                      {["Urban", "Rural"].map(a => (
                        <label key={a} className="flex-1 cursor-pointer">
                          <input type="radio" name="area" value={a} defaultChecked={a === "Urban"} className="hidden peer" />
                          <div className="py-3 text-center rounded-xl bg-[#F5F5F0] border-2 border-transparent peer-checked:border-[#5A5A40] peer-checked:bg-white transition-all text-sm font-medium">
                            {a}
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-2 ml-1">Password</label>
                    <input 
                      name="password"
                      type="password"
                      required
                      className="w-full px-5 py-4 bg-[#F5F5F0] rounded-2xl border-2 border-transparent focus:border-[#5A5A40] outline-none transition-all"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-2 ml-1">Confirm Password</label>
                    <input 
                      name="confirm"
                      type="password"
                      required
                      className="w-full px-5 py-4 bg-[#F5F5F0] rounded-2xl border-2 border-transparent focus:border-[#5A5A40] outline-none transition-all"
                    />
                  </div>
                  <button 
                    disabled={loading}
                    className="w-full py-4 bg-[#5A5A40] text-white rounded-2xl font-bold mt-4 hover:bg-[#4A4A30] transition-all disabled:opacity-50 flex items-center justify-center gap-2"
                  >
                    {loading ? <Loader2 className="animate-spin" size={20} /> : "Create Account"}
                  </button>
                </form>
              )}
            </motion.div>
          )}

          {/* --- Subject Stage --- */}
          {stage === "subject" && (
            <motion.div 
              key="subject"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 1.05 }}
              className="space-y-8"
            >
              <div className="text-center">
                <h2 className="text-3xl font-bold mb-2">Ready to learn?</h2>
                <p className="text-[#141414]/60">Select a subject to begin your adaptive quiz.</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {["English", "Mathematics", "Physics", "Chemistry"].map((s) => (
                  <button
                    key={s}
                    onClick={() => startQuiz(s, 5)}
                    className="group bg-white p-6 rounded-[24px] border border-transparent hover:border-[#5A5A40] hover:shadow-xl transition-all text-left flex items-center justify-between"
                  >
                    <div>
                      <h3 className="font-bold text-lg">{s}</h3>
                      <p className="text-xs text-[#141414]/50">Adaptive Learning Path</p>
                    </div>
                    <div className="w-10 h-10 rounded-full bg-[#F5F5F0] group-hover:bg-[#5A5A40] group-hover:text-white flex items-center justify-center transition-all">
                      <Play size={18} fill="currentColor" />
                    </div>
                  </button>
                ))}
              </div>

              {Object.keys(quiz.weakClusters).length > 0 && (
                <div className="bg-[#5A5A40]/5 p-8 rounded-[32px] border border-[#5A5A40]/10">
                  <div className="flex items-center gap-3 mb-6">
                    <History className="text-[#5A5A40]" size={24} />
                    <h3 className="font-bold text-xl">Weak Areas Found</h3>
                  </div>
                  <p className="text-sm text-[#141414]/60 mb-6">We've identified some topics you might want to revisit. Would you like to practice them specifically?</p>
                  <button 
                    onClick={() => startQuiz(quiz.subject!, 5, "weak_only", Object.keys(quiz.weakClusters).map(Number))}
                    className="w-full py-4 bg-[#5A5A40] text-white rounded-2xl font-bold hover:bg-[#4A4A30] transition-all flex items-center justify-center gap-2"
                  >
                    <RotateCcw size={20} />
                    Retry Weak Areas
                  </button>
                </div>
              )}
            </motion.div>
          )}

          {/* --- Quiz Stage --- */}
          {stage === "quiz" && quiz.currentQuestion && (
            <motion.div 
              key="quiz"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="space-y-6"
            >
              <div className="flex justify-between items-end">
                <div>
                  <span className="text-[10px] uppercase tracking-widest font-bold text-[#5A5A40] bg-[#5A5A40]/10 px-3 py-1 rounded-full">{quiz.subject}</span>
                  <h2 className="text-2xl font-bold mt-2">Question {quiz.questionIndex + 1} <span className="text-[#141414]/30 font-normal">/ {quiz.totalQuestions}</span></h2>
                </div>
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-[#141414]/40">Current Topic</p>
                  <p className="text-sm font-medium">{getTopicName(quiz.subject!, quiz.cluster)}</p>
                </div>
              </div>

              <div className="w-full h-2 bg-[#141414]/5 rounded-full overflow-hidden">
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: `${(quiz.questionIndex / quiz.totalQuestions) * 100}%` }}
                  className="h-full bg-[#5A5A40]"
                />
              </div>

              <div className="bg-white p-8 rounded-[32px] shadow-xl shadow-black/5 min-h-[400px] flex flex-col">
                <div className="flex-1">
                  <h3 className="text-xl font-medium leading-relaxed mb-8">{quiz.currentQuestion.Question}</h3>
                  
                  <div className="space-y-3">
                    {["A", "B", "C", "D"].map((key) => {
                      const optionKey = `Option ${key}` as keyof Question;
                      const isSelected = quiz.submitted && quiz.currentQuestion?.Answer === key;
                      
                      return (
                        <button
                          key={key}
                          disabled={quiz.submitted}
                          onClick={() => handleSubmitAnswer(key)}
                          className={cn(
                            "w-full p-5 rounded-2xl text-left border-2 transition-all flex items-center justify-between group",
                            !quiz.submitted && "bg-[#F5F5F0] border-transparent hover:border-[#5A5A40] hover:bg-white",
                            quiz.submitted && quiz.currentQuestion?.Answer === key && "bg-green-50 border-green-500 text-green-700",
                            quiz.submitted && quiz.currentQuestion?.Answer !== key && "bg-[#F5F5F0] border-transparent opacity-50"
                          )}
                        >
                          <span className="flex items-center gap-4">
                            <span className={cn(
                              "w-8 h-8 rounded-lg flex items-center justify-center font-bold text-xs transition-colors",
                              !quiz.submitted && "bg-white text-[#141414]/40 group-hover:bg-[#5A5A40] group-hover:text-white",
                              quiz.submitted && quiz.currentQuestion?.Answer === key && "bg-green-500 text-white"
                            )}>
                              {key}
                            </span>
                            {quiz.currentQuestion?.[optionKey]}
                          </span>
                          {quiz.submitted && quiz.currentQuestion?.Answer === key && <CheckCircle2 size={20} />}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {quiz.submitted && (
                  <motion.div 
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="mt-8 pt-8 border-t border-[#141414]/5 flex flex-col md:flex-row gap-4 items-center justify-between"
                  >
                    <div className="flex items-center gap-3">
                      {quiz.feedback.includes("✅") ? (
                        <div className="w-10 h-10 bg-green-100 text-green-600 rounded-full flex items-center justify-center">
                          <CheckCircle2 size={24} />
                        </div>
                      ) : (
                        <div className="w-10 h-10 bg-red-100 text-red-600 rounded-full flex items-center justify-center">
                          <XCircle size={24} />
                        </div>
                      )}
                      <p className="font-bold">{quiz.feedback}</p>
                    </div>

                    <div className="flex gap-3 w-full md:w-auto">
                      {!quiz.feedback.includes("✅") && (
                        <button 
                          onClick={() => handleAskAI(getTopicName(quiz.subject!, quiz.cluster), quiz.subject!)}
                          className="flex-1 md:flex-none px-6 py-3 bg-white border-2 border-[#5A5A40] text-[#5A5A40] rounded-xl font-bold hover:bg-[#5A5A40] hover:text-white transition-all flex items-center justify-center gap-2"
                        >
                          <Brain size={18} />
                          Ask AI Tutor
                        </button>
                      )}
                      <button 
                        onClick={() => {
                          if (quiz.questionIndex + 1 >= quiz.totalQuestions) {
                            finishQuiz(quiz);
                          } else {
                            setQuiz(prev => ({ ...prev, questionIndex: prev.questionIndex + 1 }));
                            loadNextQuestion({ ...quiz, questionIndex: quiz.questionIndex + 1 }, allQuestions);
                          }
                        }}
                        className="flex-1 md:flex-none px-8 py-3 bg-[#5A5A40] text-white rounded-xl font-bold hover:bg-[#4A4A30] transition-all flex items-center justify-center gap-2"
                      >
                        {quiz.questionIndex + 1 >= quiz.totalQuestions ? "Finish" : "Next"}
                        <ChevronRight size={18} />
                      </button>
                    </div>
                  </motion.div>
                )}
              </div>
            </motion.div>
          )}

          {/* --- AI Help Stage --- */}
          {stage === "help" && (
            <motion.div 
              key="help"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex flex-col h-[70vh] bg-white rounded-[32px] shadow-xl overflow-hidden"
            >
              <div className="bg-[#5A5A40] p-6 text-white">
                <div className="flex items-center gap-3 mb-1">
                  <Brain size={24} />
                  <h2 className="text-xl font-bold">AI Tutor</h2>
                </div>
                <p className="text-white/70 text-xs">Topic: {chat.activeTopic}</p>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {chat.messages.length === 0 && (
                  <div className="h-full flex flex-col items-center justify-center text-center p-8">
                    <div className="w-16 h-16 bg-[#F5F5F0] rounded-full flex items-center justify-center text-[#5A5A40] mb-4">
                      <MessageSquare size={32} />
                    </div>
                    <h3 className="font-bold text-lg mb-2">How can I help you?</h3>
                    <p className="text-sm text-[#141414]/50">I can explain concepts, give examples, or break down difficult parts of {chat.activeTopic}.</p>
                  </div>
                )}
                {chat.messages.map((msg, i) => (
                  <div key={i} className={cn(
                    "max-w-[85%] p-4 rounded-2xl text-sm leading-relaxed",
                    msg.role === "user" ? "bg-[#F5F5F0] ml-auto rounded-tr-none" : "bg-[#5A5A40] text-white mr-auto rounded-tl-none"
                  )}>
                    {msg.content}
                  </div>
                ))}
              </div>

              <div className="p-4 border-t border-[#141414]/5 space-y-4">
                <form 
                  onSubmit={(e) => {
                    e.preventDefault();
                    const input = e.currentTarget.elements.namedItem("chat_input") as HTMLInputElement;
                    sendMessage(input.value);
                    input.value = "";
                  }}
                  className="flex gap-2"
                >
                  <input 
                    name="chat_input"
                    placeholder="Type your question..."
                    className="flex-1 px-5 py-3 bg-[#F5F5F0] rounded-xl outline-none focus:ring-2 focus:ring-[#5A5A40]/20 transition-all text-sm"
                  />
                  <button className="p-3 bg-[#5A5A40] text-white rounded-xl hover:bg-[#4A4A30] transition-all">
                    <ChevronRight size={20} />
                  </button>
                </form>
                <div className="flex gap-2">
                  <button 
                    onClick={() => setStage("quiz")}
                    className="flex-1 py-2 text-xs font-bold text-[#5A5A40] hover:bg-[#5A5A40]/5 rounded-lg transition-all"
                  >
                    Back to Quiz
                  </button>
                  <button 
                    onClick={() => setStage("subject")}
                    className="flex-1 py-2 text-xs font-bold text-[#141414]/40 hover:text-[#141414] rounded-lg transition-all"
                  >
                    Main Menu
                  </button>
                </div>
              </div>
            </motion.div>
          )}

          {/* --- Finished Stage --- */}
          {stage === "finished" && (
            <motion.div 
              key="finished"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              className="text-center space-y-8"
            >
              <div className="relative inline-block">
                <div className="w-32 h-32 bg-[#5A5A40] rounded-full flex items-center justify-center text-white mx-auto shadow-2xl shadow-[#5A5A40]/30">
                  <Trophy size={64} />
                </div>
                <motion.div 
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.5, type: "spring" }}
                  className="absolute -top-2 -right-2 w-12 h-12 bg-yellow-400 rounded-full border-4 border-[#F5F5F0] flex items-center justify-center text-white font-bold"
                >
                  100%
                </motion.div>
              </div>

              <div>
                <h2 className="text-4xl font-bold mb-2">Quiz Completed!</h2>
                <p className="text-[#141414]/50">Great effort! Here's how you performed.</p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-white p-6 rounded-[24px] shadow-sm">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-1">Score</p>
                  <p className="text-3xl font-bold text-[#5A5A40]">{quiz.score} <span className="text-sm text-[#141414]/30">/ {quiz.totalQuestions}</span></p>
                </div>
                <div className="bg-white p-6 rounded-[24px] shadow-sm">
                  <p className="text-[10px] uppercase tracking-widest font-bold text-[#141414]/40 mb-1">Accuracy</p>
                  <p className="text-3xl font-bold text-[#5A5A40]">{Math.round((quiz.score / quiz.totalQuestions) * 100)}%</p>
                </div>
              </div>

              {Object.keys(quiz.weakClusters).length > 0 && (
                <div className="bg-white p-8 rounded-[32px] text-left">
                  <h3 className="font-bold text-lg mb-4 flex items-center gap-2">
                    <AlertCircle className="text-orange-500" size={20} />
                    Areas for Improvement
                  </h3>
                  <div className="space-y-3">
                    {Object.entries(quiz.weakClusters).map(([cl, count]) => (
                      <div key={cl} className="flex items-center justify-between p-4 bg-[#F5F5F0] rounded-2xl">
                        <div>
                          <p className="font-bold text-sm">{getTopicName(quiz.subject!, Number(cl))}</p>
                          <p className="text-[10px] text-[#141414]/40">{count} mistake(s)</p>
                        </div>
                        <button 
                          onClick={() => handleAskAI(getTopicName(quiz.subject!, Number(cl)), quiz.subject!)}
                          className="p-2 bg-white text-[#5A5A40] rounded-xl hover:bg-[#5A5A40] hover:text-white transition-all"
                        >
                          <Brain size={18} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-3">
                <button 
                  onClick={() => setStage("subject")}
                  className="w-full py-4 bg-[#5A5A40] text-white rounded-2xl font-bold hover:bg-[#4A4A30] transition-all"
                >
                  Back to Main Menu
                </button>
                <button 
                  onClick={() => startQuiz(quiz.subject!, 5)}
                  className="w-full py-4 bg-white border-2 border-[#5A5A40] text-[#5A5A40] rounded-2xl font-bold hover:bg-[#5A5A40]/5 transition-all"
                >
                  Try Another Quiz
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer */}
      <footer className="max-w-2xl mx-auto px-6 py-12 text-center">
        <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-[#141414]/20">Powered by EDULINE Adaptive Learning Engine</p>
      </footer>
    </div>
  );
}
