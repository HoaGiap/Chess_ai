"use strict";

// Trình duyệt KHÔNG có luật cờ vua. Mọi thứ dưới đây chỉ khớp chuỗi với
// dữ liệu máy chủ gửi: legal[].from_sq / legal[].to_sq / legal[].san.
// SAN phong cấp cũng do máy chủ tính sẵn (`a8=Q`), không dựng lại ở đây.

const FILES = "abcdefgh";
const PROMOTION_PIECES = ["Q", "R", "B", "N"];

const el = {
  squares: document.getElementById("squares"),
  pieces: document.getElementById("pieces"),
  picker: document.getElementById("picker"),
  message: document.getElementById("message"),
  moves: document.getElementById("moves"),
  top: document.getElementById("player-top"),
  bottom: document.getElementById("player-bottom"),
  topSub: document.getElementById("top-sub"),
  bottomSub: document.getElementById("bottom-sub"),
  topCaptured: document.getElementById("top-captured"),
  bottomCaptured: document.getElementById("bottom-captured"),
  undo: document.getElementById("undo"),
  topElo: document.getElementById("top-elo"),
  bottomElo: document.getElementById("bottom-elo"),
  setup: document.getElementById("setup"),
  elo: document.getElementById("elo"),
  eloValue: document.getElementById("elo-value"),
};

let state = null;
let orientation = "w";   // "w" = quân Trắng ở dưới
let selected = null;     // ô nguồn đang chọn
let promoting = null;    // { sanByLetter } đang chờ chọn quân phong cấp
let busy = false;        // đang chờ máy chủ trả lời
let aiThinking = false;  // #3B: máy đang tìm nước
let pollTimer = null;    // #3B: hẹn giờ hỏi lại
const picking = { color: "white", elo: 1200 };  // #3B: lựa chọn ở hộp thoại

// Khoá bàn và nút trong lúc đang bay, để không gửi hai nước cùng lúc —
// hai response tới lệch thứ tự thì trình duyệt lệch máy chủ vĩnh viễn.
function lockUi(locked) {
  el.squares.style.pointerEvents = locked ? "none" : "";
  for (const id of ["undo", "new", "pgn"]) {
    const button = document.getElementById(id);
    if (!button) continue;
    if (id === "undo" && state) button.disabled = locked || !state.can_undo;
    else button.disabled = locked;
  }
}

function pieceUrl(ch) {
  const white = ch === ch.toUpperCase();
  return `/static/pieces/${white ? "w" : "b"}${ch.toUpperCase()}.svg`;
}

async function api(path, method, payload) {
  const options = { method };
  if (payload !== undefined) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(payload);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch (cause) {
    // Máy chủ tắt / mạng đứt. `fetch` ném TypeError tiếng Anh — phải đổi
    // sang tiếng Việt, nếu không người chơi thấy "Failed to fetch".
    throw new Error("Không gọi được máy chủ — nó còn chạy không?");
  }
  // Phải thử đọc JSON TRƯỚC khi kiểm response.ok: 500/404-HTML hoặc
  // trang bị chắn sẽ làm response.json() ném, và thông báo tiếng Việt
  // trong body sẽ mất sạch.
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }
  if (!response.ok) {
    throw new Error(data?.error || `Máy chủ trả lỗi ${response.status}.`);
  }
  if (data === null) throw new Error("Máy chủ trả về dữ liệu không đọc được.");
  return data;
}

function boardFromFen(fen) {
  const cells = {};
  fen.split(" ")[0].split("/").forEach((row, r) => {
    let f = 0;
    for (const ch of row) {
      if (ch >= "1" && ch <= "8") { f += Number(ch); continue; }
      cells[FILES[f] + (8 - r)] = ch;
      f += 1;
    }
  });
  return cells;
}

// Vị trí trong lưới 8x8 theo hướng nhìn hiện tại.
function cellOf(name) {
  const file = FILES.indexOf(name[0]);
  const rank = Number(name[1]) - 1;
  return orientation === "w"
    ? { col: file, row: 7 - rank }
    : { col: 7 - file, row: rank };
}

// Ô ở vị trí (col,row) hiển thị là tên quân nào — chiều ngược của cellOf.
function nameOf(col, row) {
  return orientation === "w"
    ? FILES[col] + (8 - row)
    : FILES[7 - col] + (row + 1);
}

function buildSquares() {
  el.squares.innerHTML = "";
  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 8; col += 1) {
      const name = nameOf(col, row);
      const rank = Number(name[1]);
      // Màu ô theo tên quân thật, không theo vị trí hiển thị — lật bàn xong
      // màu vẫn đúng. Quy tắc: a1 là ô TỐI, h1 là ô SÁNG ("sáng bên phải").
      // (file + rank) chẵn -> sáng, lẻ -> tối. a1: 0+1 lẻ tối; h1: 7+1 chẵn sáng.
      const isDark = (FILES.indexOf(name[0]) + rank) % 2 === 1;
      const div = document.createElement("div");
      div.className = "sq " + (isDark ? "dark" : "light");
      div.dataset.sq = name;
      if (row === 7) {                       // hàng dưới cùng: nhãn cột
        const fileLabel = document.createElement("span");
        fileLabel.className = "coord file";
        fileLabel.textContent = name[0];
        div.appendChild(fileLabel);
      }
      if (col === 0) {                       // cột trái cùng: nhãn hàng
        const rankLabel = document.createElement("span");
        rankLabel.className = "coord rank";
        rankLabel.textContent = String(rank);
        div.appendChild(rankLabel);
      }
      el.squares.appendChild(div);
    }
  }
}

function legalFrom(source) {
  return state.legal.filter((m) => m.from_sq === source);
}

function paintBoard(cells) {
  el.squares.querySelectorAll(".sq").forEach((sq) => {
    sq.classList.remove("last", "sel", "check");
    sq.querySelector(".dot")?.remove();
    sq.querySelector(".ring")?.remove();
    const name = sq.dataset.sq;
    if (name === state.last_from || name === state.last_to) sq.classList.add("last");
    if (name === selected) sq.classList.add("sel");
    // Máy chủ đã nói ô nào đang bị chiếu. Trình duyệt không tự suy ra:
    // "vua nào bị chiếu" là luật cờ vua, không phải trình bày.
    if (state.check && name === state.check_square) sq.classList.add("check");
  });
  if (!selected) return;
  // Nhiều nước đi có thể CÙNG một ô đích — tốt b7 vừa bắt a8/c8 vừa phong cấp
  // b8=Q/R/B/N. Chỉ vẽ MỘT dấu mỗi ô, nếu không ô bắt sẽ có 4 vòng tròn chồng.
  const byTarget = new Map();
  for (const option of legalFrom(selected)) {
    if (!byTarget.has(option.to_sq)) byTarget.set(option.to_sq, option);
  }
  for (const [to, option] of byTarget) {
    const sq = el.squares.querySelector(`[data-sq="${to}"]`);
    if (!sq) continue;
    const mark = document.createElement("div");
    mark.className = option.capture ? "ring" : "dot";
    sq.appendChild(mark);
  }
}

function paintPieces(cells) {
  // Quân vừa đi phải GIỮ node cũ và chỉ đổi khoá `data-sq`, để transform
  // đổi và CSS transition trượt nó. Nếu xoá rồi tạo node mới, transition
  // không bao giờ kích hoạt — quân biến mất rồi xuất hiện ở chỗ mới.
  // Phong cấp (P -> Q) không khớp nên rơi về tạo node mới; chấp nhận được.
  if (state.last_from && state.last_to) {
    const moved = el.pieces.querySelector(`.piece[data-sq="${state.last_from}"]`);
    const landed = cells[state.last_to];
    if (moved && landed === moved.dataset.ch) {
      moved.dataset.sq = state.last_to;
    }
  }
  el.pieces.querySelectorAll(".piece").forEach((node) => {
    if (cells[node.dataset.sq] !== node.dataset.ch) node.remove();
  });
  Object.entries(cells).forEach(([name, ch]) => {
    let node = el.pieces.querySelector(`[data-sq="${name}"]`);
    if (!node) {
      node = document.createElement("div");
      node.className = "piece";
      node.dataset.ch = ch;
      node.dataset.sq = name;
      const img = document.createElement("img");
      img.src = pieceUrl(ch);
      img.alt = "";
      node.appendChild(img);
      el.pieces.appendChild(node);
    }
    const { col, row } = cellOf(name);
    node.style.transform = `translate(${col * 100}%, ${row * 100}%)`;
  });
}

function paintPanel() {
  const whiteTurn = state.turn === "white";
  el.top.classList.toggle("turn", !whiteTurn);
  el.bottom.classList.toggle("turn", whiteTurn);
  el.topSub.textContent = whiteTurn ? "Đang đợi" : "Đến lượt";
  el.bottomSub.textContent = whiteTurn ? "Đến lượt" : "Đang đợi";
  el.topCaptured.innerHTML = state.captured_by_white
    .map((p) => `<img src="${pieceUrl(p)}" alt="">`).join("");
  el.bottomCaptured.innerHTML = state.captured_by_black
    .map((p) => `<img src="${pieceUrl(p)}" alt="">`).join("");

  el.moves.innerHTML = "";
  for (let i = 0; i < state.moves.length; i += 2) {
    const number = document.createElement("li");
    number.textContent = `${i / 2 + 1}.`;
    const white = document.createElement("li");
    white.className = "w";
    white.textContent = state.moves[i];
    const black = document.createElement("li");
    black.className = "b";
    black.textContent = state.moves[i + 1] ?? "";
    if (i + 1 === state.moves.length - 1) black.classList.add("now");
    el.moves.append(number, white, black);
  }
  el.moves.scrollTop = el.moves.scrollHeight;
  el.undo.disabled = !state.can_undo;
  // Nhãn Elo và "AI đang nghĩ" phải theo PHE MÁY, không theo phe đang đi:
  // hàng trên luôn là Đen, hàng dưới luôn là Trắng, còn máy có thể là phe
  // nào tuỳ người chơi chọn. Trước đây gắn theo `turn` nên khi người chơi
  // chọn phe Đen, nhãn hiện nhầm sang phe Trắng.
  const coMay = state.human_color !== null;
  const mayLaPheDen = state.human_color === "white";   // người chơi trắng → máy đen
  const mayDangNghi = aiThinking;
  const nhanhMay = mayDangNghi ? "AI đang nghĩ" : "Elo " + state.elo;
  el.topElo.textContent = coMay && mayLaPheDen ? nhanhMay : "";
  el.bottomElo.textContent = coMay && !mayLaPheDen ? nhanhMay : "";
  el.top.classList.toggle("thinking", coMay && mayLaPheDen && mayDangNghi);
  el.bottom.classList.toggle("thinking", coMay && !mayLaPheDen && mayDangNghi);
  el.squares.classList.toggle(
    "locked", coMay && (state.over || state.turn !== state.human_color),
  );
  if (state.over) {
    el.message.textContent = state.result_text;
    el.message.classList.remove("error");
  }
}

function apply(next) {
  // Chỉ khi là VÁN MỚI mới tự đặt hướng bàn theo phe người chơi. Nếu đặt mỗi
  // nước đi thì nút "Lật bàn" sẽ bị ghi đè ngay lần sau — mà người chơi cần
  // xem ngược lại bàn khi đấu máy.
  const doiVan = state === null || state.game_id !== next.game_id;
  state = next;
  aiThinking = next.thinking;
  selected = null;
  hidePicker();
  if (doiVan) {
    const wanted = next.human_color === "black" ? "b" : "w";
    if (wanted !== orientation) {
      orientation = wanted;
      buildSquares();
    }
  }
  const cells = boardFromFen(state.fen);
  paintPieces(cells);
  paintBoard(cells);
  paintPanel();
  if (aiThinking) pollAi(); else stopPolling();
  showInUrl(state.game_id);
}

// ---- #3B: hỏi lại cho tới khi máy đi xong ------------------------------
// Máy tìm nước ở thread nền, nên POST /move trả về ngay. Trình duyệt hỏi
// GET cho tới khi `thinking` là false.

function stopPolling() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null; }
}

function pollAi() {
  stopPolling();
  pollTimer = setTimeout(async () => {
    pollTimer = null;
    try {
      const next = await api(`/api/game/${state.game_id}`, "GET");
      // Người chơi có thể đã bấm Ván mới / Lùi trong lúc chờ; khi đó response
      // này là của ván CŨ và sẽ đè bàn ngược lại. Bỏ qua nếu ván đã đổi.
      if (state === null || state.game_id !== next.game_id) return;
      apply(next);
    } catch (error) {
      aiThinking = false;
      stopPolling();
      el.squares.classList.remove("locked");
      say(error.message, true);
    }
  }, 300);
}

function say(text, isError = false) {
  el.message.textContent = text;
  el.message.classList.toggle("error", isError);
}

function hidePicker() {
  promoting = null;
  el.picker.hidden = true;
  el.picker.innerHTML = "";
}

function showPicker(options, target) {
  // Khoá theo `promotion` (tên quân), KHÔNG theo ký tự cuối của SAN: SAN
  // phong cấp kèm chiếu có đuôi `+` (g8=Q+) nên slice(-1) ra "+", bấm Q sẽ
  // gửi san=undefined và hỏng.
  promoting = { sanByLetter: {} };
  for (const o of options) promoting.sanByLetter[o.promotion] = o.san;
  el.picker.hidden = false;
  el.picker.innerHTML = "";
  const { col, row } = cellOf(target);
  el.picker.style.transform = `translate(${col * 100}%, ${row * 100}%)`;
  PROMOTION_PIECES.forEach((letter) => {
    const button = document.createElement("button");
    button.title = "Phong cấp " + letter;
    const img = document.createElement("img");
    img.src = pieceUrl(letter);
    img.alt = letter;
    button.appendChild(img);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const san = promoting.sanByLetter[letter];
      hidePicker();
      send(san);
    });
    el.picker.appendChild(button);
  });
}

async function send(san) {
  if (busy) return;           // đang bay: bỏ qua, nếu không sẽ gửi 2 nước
  busy = true;
  lockUi(true);
  try {
    const next = await api(`/api/game/${state.game_id}/move`, "POST", { san });
    say("");                 // xoá thông báo cũ TRƯỚC khi vẽ
    apply(next);             // nếu vừa kết thúc, paintPanel mới là người viết
  } catch (error) {
    say(error.message, true);   // bàn cờ KHÔNG đổi
  } finally {
    busy = false;
    lockUi(false);
  }
}

el.squares.addEventListener("click", (event) => {
  const sq = event.target.closest(".sq");
  if (!sq || !state || state.over || busy) return;
  // Review Focus 5: bấm vào quân của máy thì không được hiện chấm tròn nào,
  // cũng không được gửi gì lên máy chủ.
  if (state.human_color !== null && state.turn !== state.human_color) {
    say("Đến lượt máy.");
    return;
  }
  const name = sq.dataset.sq;

  // Đang chờ chọn quân phong cấp thì bấm ô nào cũng chỉ huỷ, không đi nước nào.
  // Phải nằm Ở ĐÂY chứ không bắt sự kiện trên el.board: cùng một cú bấm mở hộp
  // cũng nổi lên el.board và sẽ huỷ hộp ngay lập tức.
  if (promoting) {
    hidePicker();
    paintBoard(boardFromFen(state.fen));
    return;
  }

  if (selected === name) {          // bấm lại ô nguồn để bỏ chọn
    selected = null;
    paintBoard(boardFromFen(state.fen));
    return;
  }

  if (selected) {
    const options = legalFrom(selected).filter((m) => m.to_sq === name);
    if (options.length === 0) {
      say("Ô đó không phải nước đi hợp lệ từ ô đang chọn.");
      return;
    }
    if (options[0].promotion) {
      showPicker(options, name);
      return;
    }
    send(options[0].san);
    return;
  }

  if (legalFrom(name).length > 0) {
    selected = name;
    paintBoard(boardFromFen(state.fen));
  } else {
    say("Chọn một quân của bạn để đi.");
  }
});

// Nút này dùng chung cho cả 4 hành động, nên mọi nơi đều phải qua đây —
// `state` có thể còn null nếu POST /api/game lúc mở trang thất bại.
async function withState(action) {
  if (!state) {
    say("Chưa có ván nào. Bấm 'Ván mới' để bắt đầu.", true);
    return;
  }
  try {
    const next = await action(state);
    say("");
    apply(next);
  } catch (error) {
    say(error.message, true);
  }
}

el.undo.addEventListener("click", () => {
  stopPolling();            // xem lý do o trên
  aiThinking = false;
  withState((s) => api(`/api/game/${s.game_id}/undo`, "POST"));
});

document.getElementById("flip").addEventListener("click", () => {
  if (!state) return;
  orientation = orientation === "w" ? "b" : "w";
  buildSquares();
  apply(state);
});

// Ưu tiên route /new của ván đang chơi (nó có tồn tại vì `new_game` giữ cấu
// hình Session cho #3B); chỉ tạo ván mới khi chưa có ván nào.
document.getElementById("new").addEventListener("click", () => {
  // Đang đấu máy thì giữ cấu hình, chỉ bắt đầu ván mới. Chưa đấu thì hỏi
  // phe và Elo trước — không có AI thì các lựa chọn đó chẳng dùng để làm gì.
  if (state && state.human_color !== null) {
    stopPolling();          // response poll dang bay se den sau, de ban nguoc lai
    aiThinking = false;
    withState((s) => api(`/api/game/${s.game_id}/new`, "POST"));
    return;
  }
  el.setup.hidden = false;
});

document.getElementById("pgn").addEventListener("click", () => withState(async (s) => {
  const { pgn } = await api(`/api/game/${s.game_id}/pgn`, "GET");
  const url = URL.createObjectURL(new Blob([pgn], { type: "application/x-chess-pgn" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = "chess-ai.pgn";
  link.click();
  URL.revokeObjectURL(url);
  return s;   // không đổi bàn cờ
}));

document.getElementById("pick-color").addEventListener("click", (event) => {
  const nut = event.target.closest("button[data-color]");
  if (!nut) return;
  for (const b of document.querySelectorAll("#pick-color button")) {
    b.classList.toggle("on", b === nut);
  }
  picking.color = nut.dataset.color;
});

el.elo.addEventListener("input", () => {
  picking.elo = Number(el.elo.value);
  el.eloValue.textContent = String(picking.elo);
});

document.getElementById("start").addEventListener("click", async () => {
  lockUi(true);
  try {
    const human = picking.color === "both" ? null : picking.color;
    const next = await api("/api/game", "POST", {
      human_color: human,
      elo: picking.elo,
    });
    el.setup.hidden = true;
    say("");
    apply(next);
  } catch (error) {
    say(error.message, true);
  } finally {
    lockUi(false);
  }
});

const themeButton = document.getElementById("theme");
function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("chessai-theme", theme);
}
themeButton.addEventListener("click", () => {
  setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
const savedTheme = localStorage.getItem("chessai-theme");
if (savedTheme) setTheme(savedTheme);
else if (window.matchMedia("(prefers-color-scheme: light)").matches) setTheme("light");

// game_id nằm trong query string: http://.../?g=xxxx
// Nhờ vậy F5 không mất ván, và copy link sang máy khác cũng vào đúng ván.
function showInUrl(gameId) {
  const url = new URL(location.href);
  url.searchParams.set("g", gameId);
  history.replaceState(null, "", url);
}

async function loadOrCreateGame() {
  const fromUrl = new URLSearchParams(location.search).get("g");
  if (fromUrl) {
    try {
      return await api(`/api/game/${encodeURIComponent(fromUrl)}`, "GET");
    } catch (error) {
      // Máy chủ khởi động lại là mất ván — nói rõ rồi mở ván mới.
      say("Ván trong liên kết không còn trên máy chủ — đã mở ván mới.");
    }
  }
  return await api("/api/game", "POST");
}

buildSquares();
try {
  apply(await loadOrCreateGame());
} catch (error) {
  say(error.message, true);
}
