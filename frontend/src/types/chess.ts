/** Shared types for the Chess module — mirror the backend Pydantic responses. */

export type ChessScopeType = "global" | "department";

export type ChessGameSummary = {
  id: string;
  slug?: string | null;
  white?: string | null;
  black?: string | null;
  result?: string | null;
  eco?: string | null;
  opening_name?: string | null;
  white_elo?: number | null;
  black_elo?: number | null;
  event?: string | null;
  played_at?: string | null;
  ply_count: number;
  source_game: string;
  scope_type: ChessScopeType;
  scope_id?: string | null;
  created_at: string;
};

export type GameAnalysisMove = {
  ply: number;
  san: string;
  side: "white" | "black";
  class: "blunder" | "mistake" | "inaccuracy" | "ok";
};

export type GameAnalysis = {
  evals: number[]; // white-POV centipawns per position
  moves: GameAnalysisMove[];
  summary: { blunder: number; mistake: number; inaccuracy: number };
};

export type ChessGameDetail = ChessGameSummary & {
  pgn: string;
  headers: Record<string, string>;
  final_fen?: string | null;
  knowledge_type_slugs: string[];
  analysis_status: "none" | "queued" | "running" | "done" | "error";
  analysis_json?: GameAnalysis | null;
};

export type ChessPuzzle = {
  id: string;
  slug?: string | null;
  fen: string;
  side_to_move: "w" | "b";
  themes: string[];
  rating?: number | null;
  title?: string | null;
  description?: string | null;
  is_published: boolean;
  scope_type: ChessScopeType;
  scope_id?: string | null;
  created_at: string;
  // Present only for coaches / in attempt responses.
  solution_moves?: string[];
};

export type PuzzleAttemptResult = {
  solved: boolean;
  solution_moves: string[];
  attempt_id: string;
};

export type PuzzleStats = {
  attempts: number;
  solved: number;
  accuracy: number;
  rating?: number;
};

export type ChessPositionSource = "manual" | "game" | "puzzle";

export type ChessPosition = {
  id: string;
  slug?: string | null;
  fen: string;
  label?: string | null;
  description?: string | null;
  eval_cp?: number | null;
  best_move?: string | null;
  eval_depth?: number | null;
  themes: string[];
  difficulty?: number | null;
  popularity?: number | null;
  nb_plays?: number | null;
  piece_count?: number | null;
  side_to_move?: "w" | "b" | null;
  eco?: string | null;
  opening_name?: string | null;
  source?: ChessPositionSource | null;
  source_puzzle_id?: string | null;
  scope_type: ChessScopeType;
  scope_id?: string | null;
  created_at: string;
};

export type FacetCount = { value: string; count: number };

export type PositionFacets = {
  themes: FacetCount[];
  openings: FacetCount[];
  sources: FacetCount[];
  difficulty: { min: number | null; max: number | null } | null;
  piece_count: { min: number | null; max: number | null } | null;
};

export type ChessMatchMove = {
  uci: string;
  san: string;
  fen: string;
  by: "white" | "black" | "engine";
};

export type ChessMatch = {
  id: string;
  white_employee_id?: string | null;
  black_employee_id?: string | null;
  mode: "human_vs_engine" | "human_vs_human";
  engine_level?: number | null;
  status: "pending" | "active" | "finished" | "aborted";
  current_fen: string;
  moves: ChessMatchMove[];
  result?: string | null;
  winner_employee_id?: string | null;
  game_id?: string | null;
  your_color?: "white" | "black" | null;
  created_at: string;
  updated_at: string;
};

export type Paginated<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

/** A single analysis line from the engine. */
export type EngineLine = {
  depth: number;
  /** Centipawn score from the side-to-move POV (positive = better for mover). */
  scoreCp: number | null;
  /** Mate-in-N (signed) when the engine reports a forced mate. */
  mate: number | null;
  /** Principal variation as UCI moves. */
  pv: string[];
};
