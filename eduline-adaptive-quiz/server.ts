import express from "express";
import { createServer as createViteServer } from "vite";
import path from "path";
import { fileURLToPath } from "url";
import Database from "better-sqlite3";
import fs from "fs";
import { parse } from "csv-parse/sync";
import cors from "cors";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DB_PATH = "eduline.db";
const QUESTIONS_CSV = "cleaned_mcqs_clustered.csv";

// Initialize Database
const db = new Database(DB_PATH);
db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_uuid TEXT UNIQUE,
    name TEXT,
    area TEXT,
    password TEXT,
    created_at TEXT
  );
  CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_uuid TEXT,
    subject TEXT,
    score INTEGER,
    total_questions INTEGER,
    progress REAL,
    weak_clusters_json TEXT,
    taken_at TEXT
  );
`);

// Load Questions from CSV
let questions: any[] = [];
try {
  const fileContent = fs.readFileSync(QUESTIONS_CSV, "utf-8");
  questions = parse(fileContent, {
    columns: true,
    skip_empty_lines: true,
  });
  console.log(`Loaded ${questions.length} questions from CSV.`);
} catch (error) {
  console.error("Error loading questions CSV:", error);
}

async function startServer() {
  const app = express();
  const PORT = 3000;

  app.use(cors());
  app.use(express.json());

  // API Routes
  app.post("/api/register", (req, res) => {
    const { student_uuid, name, area, password } = req.body;
    try {
      const stmt = db.prepare(
        "INSERT INTO users (student_uuid, name, area, password, created_at) VALUES (?, ?, ?, ?, ?)"
      );
      stmt.run(student_uuid, name, area, password, new Date().toISOString());
      res.json({ success: true, student_uuid });
    } catch (error: any) {
      res.status(400).json({ error: error.message });
    }
  });

  app.post("/api/login", (req, res) => {
    const { student_uuid, password } = req.body;
    const user = db
      .prepare("SELECT student_uuid, name, area FROM users WHERE student_uuid = ? AND password = ?")
      .get(student_uuid, password) as any;

    if (user) {
      res.json({ success: true, user });
    } else {
      res.status(401).json({ error: "Invalid credentials" });
    }
  });

  app.get("/api/questions", (req, res) => {
    const { subject } = req.query;
    const filtered = questions.filter((q) => q.Subject === subject);
    res.json(filtered);
  });

  app.post("/api/results", (req, res) => {
    const { student_uuid, subject, score, total_questions, progress, weak_clusters } = req.body;
    try {
      const stmt = db.prepare(
        "INSERT INTO results (student_uuid, subject, score, total_questions, progress, weak_clusters_json, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
      );
      stmt.run(
        student_uuid,
        subject,
        score,
        total_questions,
        progress,
        JSON.stringify(weak_clusters),
        new Date().toISOString()
      );
      res.json({ success: true });
    } catch (error: any) {
      res.status(400).json({ error: error.message });
    }
  });

  app.get("/api/results/:student_uuid", (req, res) => {
    const { student_uuid } = req.params;
    const results = db
      .prepare("SELECT * FROM results WHERE student_uuid = ? ORDER BY taken_at DESC")
      .all(student_uuid);
    res.json(results);
  });

  // Vite middleware for development
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
