/**
 * Lightweight i18n — no framework, no provider. `t("English source")` returns
 * the Vietnamese translation when present, else the source string. Default
 * locale is Vietnamese (the company is Cờ vua Dương Sinh); a future English
 * toggle can flip `locale` and add an `en` dictionary.
 *
 * Usage:  import { t } from "@/lib/i18n";  <h1>{t("Games")}</h1>
 */

type Dict = Record<string, string>;

const vi: Dict = {
  // ── Navigation / shell ──
  "Dashboard": "Tổng quan",
  "Org Knowledge": "Tri thức",
  "Documents": "Tài liệu",
  "Wiki": "Wiki",
  "Reviews": "Duyệt bài",
  "AI Skills": "Kỹ năng AI",
  "Chess": "Cờ vua",
  "Chess Wiki": "Wiki Cờ vua",
  "Organization": "Tổ chức",
  "Departments": "Phòng ban",
  "Employees": "Nhân sự",
  "System": "Hệ thống",
  "Audit Log": "Nhật ký",
  "Settings": "Cài đặt",
  "Backup & Restore": "Sao lưu & Khôi phục",
  "Profile": "Hồ sơ",
  "Sign out": "Đăng xuất",

  // ── Chess nav items ──
  "Games": "Ván cờ",
  "Analysis": "Phân tích",
  "Puzzles": "Bài tập",
  "Play": "Đấu tập",
  "Positions": "Thế cờ",
  "Study sets": "Bộ học liệu",
  "Classes": "Lớp học",

  // ── Chess dashboard ──
  "Game database, engine analysis, and tactics training for Dương Sinh Chess.":
    "Kho ván đấu, phân tích bằng engine và luyện chiến thuật — Cờ vua Dương Sinh.",
  "Browse and import the game database (PGN).": "Duyệt và nhập kho ván đấu (PGN).",
  "Play out positions with the Stockfish engine.": "Đánh thử thế cờ với engine Stockfish.",
  "Train tactics and track your progress.": "Luyện chiến thuật và theo dõi tiến độ.",
  "Add games from a .pgn file or pasted text.": "Thêm ván từ file .pgn hoặc dán văn bản.",
  "Import PGN": "Nhập PGN",
  "Your puzzle progress": "Tiến độ bài tập của bạn",
  "solved": "đã giải",
  "attempts": "lượt thử",
  "accuracy": "độ chính xác",

  // ── Games ──
  "Search by player, opening, or event…": "Tìm theo kỳ thủ, khai cuộc, giải đấu…",
  "Search": "Tìm",
  "No games yet": "Chưa có ván nào",
  "Import a PGN file to build your game database.": "Nhập file PGN để xây kho ván đấu.",
  "White": "Trắng",
  "Black": "Đen",
  "Result": "Kết quả",
  "Opening": "Khai cuộc",
  "Date": "Ngày",
  "Moves": "Số nước",
  "Previous": "Trước",
  "Next": "Sau",
  "Back to Chess": "← Về Cờ vua",
  "Delete": "Xoá",
  "Analyze final position": "Phân tích thế cờ cuối",
  "Back to Games": "← Về Ván cờ",
  "Flip": "Lật bàn",

  // ── Analysis ──
  "Play moves on the board; Stockfish evaluates the position live.":
    "Đi quân trên bàn; Stockfish đánh giá thế cờ trực tiếp.",
  "Paste a FEN to load a position…": "Dán FEN để nạp thế cờ…",
  "Load": "Nạp",
  "Undo": "Hoàn tác",
  "Reset": "Đặt lại",

  // ── Puzzles ──
  "Tactics training": "Luyện chiến thuật",
  "Loading puzzle…": "Đang tải bài tập…",
  "All caught up!": "Đã giải hết!",
  "No puzzles available": "Chưa có bài tập",
  "Find the best move": "Tìm nước đi tốt nhất",
  "White to move.": "Trắng đi.",
  "Black to move.": "Đen đi.",
  "Correct! Replay the full line on the board.": "Chính xác! Xem lại toàn bộ đòn trên bàn cờ.",
  "Not the best move — see the solution on the board.": "Chưa phải nước hay nhất — xem lời giải trên bàn cờ.",
  "Next puzzle": "Bài tiếp theo",
  "Show solution": "Hiện lời giải",

  // ── Play (sparring) ──
  "Play against the engine or a colleague.": "Đấu với engine hoặc đồng nghiệp.",
  "Your color": "Màu của bạn",
  "Engine level": "Cấp độ engine",
  "Play vs Engine": "Đấu với Engine",
  "Your matches": "Ván của bạn",
  "No matches yet": "Chưa có ván đấu",
  "Start one above.": "Tạo một ván ở trên.",
  "Mode": "Chế độ",
  "Status": "Trạng thái",
  "Your move": "Lượt của bạn",
  "Resign": "Đầu hàng",
  "Engine thinking…": "Engine đang nghĩ…",
  "Waiting for opponent…": "Đang chờ đối thủ…",
  "Opponent to move": "Lượt đối thủ",
  "No moves yet.": "Chưa có nước đi.",
  "View archived game →": "Xem ván đã lưu →",
  "Back to Play": "← Về Đấu tập",

  // ── Positions ──
  "Save and revisit FEN positions.": "Lưu và xem lại các thế cờ FEN.",
  "Label (optional)": "Nhãn (tuỳ chọn)",
  "Save": "Lưu",
  "Valid FEN": "FEN hợp lệ",
  "Invalid FEN": "FEN không hợp lệ",
  "No saved positions": "Chưa có thế cờ nào",
  "Save a FEN above to revisit it later.": "Lưu một FEN ở trên để xem lại sau.",
  "Untitled": "Chưa đặt tên",
  "Analyze →": "Phân tích →",

  // ── Study sets ──
  "Curated collections of games, puzzles and positions.":
    "Bộ sưu tập ván đấu, bài tập và thế cờ được biên soạn.",
  "New study set": "Bộ học liệu mới",
  "Create": "Tạo",
  "No study sets yet": "Chưa có bộ học liệu",
  "Note (optional)": "Ghi chú (tuỳ chọn)",
  "Add": "Thêm",
  "No items yet.": "Chưa có mục nào.",
  "Open game →": "Mở ván →",
  "Back to Study sets": "← Về Bộ học liệu",

  // ── Chess Wiki (specialized knowledge base) ──
  "Specialized chess knowledge for teachers — openings, tactics, endgames, strategy and model games.":
    "Kiến thức cờ vua chuyên ngành cho giáo viên — khai cuộc, chiến thuật, tàn cuộc, chiến lược và ván mẫu.",
  "New page": "Trang mới",
  "Propose page": "Đề xuất trang",
  "Search the chess wiki…": "Tìm trong Wiki Cờ vua…",
  "No chess wiki pages yet": "Chưa có trang wiki cờ vua nào",
  "Create a page or publish a lesson to the wiki to start building chess knowledge.":
    "Tạo trang mới hoặc xuất bản bài giảng lên wiki để bắt đầu xây dựng kho kiến thức cờ vua.",
  "No pages match your search.": "Không có trang nào khớp tìm kiếm.",
};

const dicts: Record<string, Dict> = { vi };

let locale = "vi";
if (typeof window !== "undefined") {
  locale = localStorage.getItem("arkon_locale") || "vi";
}

export function getLocale(): string {
  return locale;
}

export function setLocale(l: string): void {
  locale = l;
  if (typeof window !== "undefined") localStorage.setItem("arkon_locale", l);
}

/** Translate an English source string. Falls back to the source when missing. */
export function t(source: string): string {
  return dicts[locale]?.[source] ?? source;
}
