export interface User {
  student_uuid: string;
  name: string;
  area: string;
}

export interface Question {
  Subject: string;
  Cluster: number;
  Question: string;
  "Option A": string;
  "Option B": string;
  "Option C": string;
  "Option D": string;
  Answer: string;
}

export interface QuizState {
  started: boolean;
  subject: string | null;
  cluster: number;
  questionIndex: number;
  totalQuestions: number;
  score: number;
  usedIndices: number[];
  currentQuestion: Question | null;
  submitted: boolean;
  feedback: string;
  weakClusters: Record<number, number>;
  mode: "normal" | "weak_only";
  weakOnlyList: number[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatState {
  messages: ChatMessage[];
  activeTopic: string | null;
  activeSubject: string | null;
}

export const CLUSTER_TOPICS: Record<number, Record<string, string>> = {
  0: {
    English: "Formal Letters & Vocabulary",
    Mathematics: "Algebra (Quadratics & Roots)",
    Physics: "Gas Properties",
    Chemistry: "Coal & Combustion",
  },
  1: {
    English: "Speech Forms & Simplification",
    Mathematics: "Simplification & Expressions",
    Physics: "General Concepts",
    Chemistry: "Carbon & Oxides",
  },
  2: {
    English: "Synonyms & Vocabulary",
    Mathematics: "Terms & Differences",
    Physics: "Units & Measurements",
    Chemistry: "Acids & Reactions",
  },
  3: {
    English: "Essay Writing & Summary",
    Mathematics: "General Concepts",
    Physics: "General Concepts",
    Chemistry: "Industrial Processes & Raw Materials",
  },
  4: {
    English: "Idioms & Word Choice",
    Mathematics: "Sequences (GP) & Terms",
    Physics: "Gas Processes",
    Chemistry: "General Concepts",
  },
  5: {
    English: "Advanced Vocabulary",
    Mathematics: "Algebra (x², 2x) & Variation",
    Physics: "Electricity, Sound & Current",
    Chemistry: "Salts",
  },
  6: {
    English: "Phrasal Verbs & Word Meanings",
    Mathematics: "Logarithms (log₁₀) & Formulas",
    Physics: "Heat",
    Chemistry: "General Concepts",
  },
  7: {
    English: "Antonyms & Opposites",
    Mathematics: "Geometry (Area, Radius, Height)",
    Physics: "General Concepts",
    Chemistry: "Compounds",
  },
  8: {
    English: "Multiple Choice Vocabulary",
    Mathematics: "Probability & Numbers",
    Physics: "General Concepts",
    Chemistry: "Ions & Trioxocarbonates",
  },
};

export const CLUSTER_LIMITS: Record<string, number> = {
  English: 8,
  Mathematics: 8,
  Physics: 8,
  Chemistry: 8,
};
