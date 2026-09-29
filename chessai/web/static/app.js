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
  boardArea: document.getElementById("board-area"),
  roomStatus: document.getElementById("room-status"),
  roomCode: document.getElementById("room-code"),
  roomCodeBig: document.getElementById("room-code-big"),
  seatWhite: document.getElementById("seat-white"),
  seatBlack: document.getElementById("seat-black"),
  invite: document.getElementById("invite"),
  roomNote: document.getElementById("room-note"),
  startRoom: document.getElementById("start-room"),
  roomList: document.getElementById("room-list"),
  resign: document.getElementById("resign"),
  rematch: document.getElementById("rematch"),
  forfeit: document.getElementById("forfeit"),
  newGame: document.getElementById("new"),
  leaveRoom: document.getElementById("leave-room"),
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

// ---- #3C: phòng chơi người thật ----
let playerToken = localStorage.getItem("chessai-player") || "";
let view = "home";           // "home" | "lobby" | "room" | "game"
let room = null;             // RoomView hiện tại
let socket = null;           // WebSocket
let roomPollTimer = null;    // dự phòng khi WebSocket không mở được

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

async function api(path, method, payload, extraHeaders) {
  const options = { method, headers: { ...(extraHeaders || {}) } };
  if (payload !== undefined) {
    options.headers["Content-Type"] = "application/json";
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
  // Trong phòng chơi người thật thì KHÔNG có máy: hiện "Elo 0" hay
  // "AI đang nghĩ" là vô nghĩa. `is_room` đánh dấu trạng thái đó.
  const coMay = state.human_color !== null && !state.is_room;
  const mayLaPheDen = state.human_color === "white";   // người chơi trắng → máy đen
  const mayDangNghi = aiThinking;
  const nhanhMay = mayDangNghi ? "AI đang nghĩ" : "Elo " + state.elo;
  el.topElo.textContent = coMay && mayLaPheDen ? nhanhMay : "";
  el.bottomElo.textContent = coMay && !mayLaPheDen ? nhanhMay : "";
  el.top.classList.toggle("thinking", coMay && mayLaPheDen && mayDangNghi);
  el.bottom.classList.toggle("thinking", coMay && !mayLaPheDen && mayDangNghi);
  const laLuotNguoi = state.human_color === null || state.turn === state.human_color;
  el.squares.classList.toggle("locked", !laLuotNguoi || state.over);
  if (state.over) {
    el.message.textContent = state.result_text;
    el.message.classList.remove("error");
  }
}

function apply(next) {
  // Phòng dùng applyRoomGame (có bàn xoay theo ghế), không đi qua đây.
  if (inRoom()) return;
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
  if (inRoom()) { await guiNuocPhong(san); return; }
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
    say(inRoom() ? "Chưa đến lượt bạn." : "Đến lượt máy.");
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


// ---- #3C: phòng chơi người thật ------------------------------------------------
// Máy chủ giữ toàn bộ luật cờ vua. Trình duyệt ở đây chỉ khớp chuỗi với
// RoomState mà máy chủ gửi xuống: `data.room` (ghế, trạng thái) và
// `data.game` (đúng GameState mà #3A đã dùng).

async function apiRoom(path, method = "GET", payload) {
  if (!playerToken) {
    playerToken = (await api("/api/me", "GET")).player;
    localStorage.setItem("chessai-player", playerToken);
  }
  return api(path, method, payload, { "X-Player": playerToken });
}

// Đang ở phòng chơi hay không — KHÔNG suy từ `view`. Biến `view` có giá trị
// "game" cho cả ván bình thường lẫn phòng chơi, nên dùng nó để rẽ nhánh thì
// nút "Hai bên" vẽ bàn trắng và bấm ô không có phản ứng.
const inRoom = () => room !== null;

function showView(ten) {
  view = ten;
  for (const id of ["home", "lobby", "room"]) {
    document.getElementById("view-" + id).hidden = id !== ten;
  }
  for (const b of document.querySelectorAll("#tabs button")) {
    b.classList.toggle("on", b.dataset.view === (ten === "game" ? "lobby" : ten));
  }
  const vanPhong = ten === "room" || ten === "game";
  el.setup.hidden = true;
  el.undo.hidden = vanPhong;          // C4: trong phòng không lùi nước
  // "Ván mới" gọi `POST /api/game/{id}/new` — trên ván phòng mà bấm là xoá
  // cả ván đang đấu, nên phải ẩn.
  el.newGame.hidden = vanPhong;
  el.leaveRoom.hidden = !vanPhong;
  el.resign.hidden = !vanPhong;
  el.rematch.hidden = !(vanPhong && room && room.started && state && state.over);
  el.forfeit.hidden = true;
  el.roomStatus.hidden = !vanPhong;
}

function renderRoom() {
  if (!room) return;
  el.roomCodeBig.textContent = room.id;
  el.seatWhite.textContent = room.white ? "có người" : "trống";
  el.seatBlack.textContent = room.black ? "có người" : "trống";
  el.invite.value = location.origin + "/?room=" + room.id;
  const laHost = room.host_is_you;
  const duHai = room.seat_white && room.seat_black;
  el.startRoom.disabled = room.started || !(laHost && duHai);
  el.startRoom.textContent = room.started ? "Ván đang đấu" : "Bắt đầu";
  const ghe = room.you === "white" ? "Trắng" : room.you === "black" ? "Đen" : null;
  if (!ghe) {
    el.roomNote.textContent =
      "Bạn không ngồi ghế nào trong phòng này — chỉ xem được.";
  } else if (room.started) {
    el.roomNote.textContent = `Bạn đang đánh phe ${ghe}.`;
  } else if (laHost) {
    el.roomNote.textContent = "Bạn là người tạo phòng — chờ đối thủ rồi bấm Bắt đầu.";
  } else {
    el.roomNote.textContent = "Chờ người tạo phòng bấm Bắt đầu.";
  }
}

function renderLobby(danh) {
  el.roomList.innerHTML = "";
  if (danh.length === 0) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Chưa có phòng nào. Bấm “Tạo phòng” để mở một phòng.";
    el.roomList.appendChild(li);
    return;
  }
  for (const r of danh) {
    const li = document.createElement("li");
    const ma = document.createElement("span");
    ma.className = "ma";
    ma.textContent = r.id;
    const trang = document.createElement("span");
    trang.className = "trang";
    trang.textContent = r.status;
    const nut = document.createElement("button");
    nut.textContent = "Vào";
    // Đã đủ hai người, hoặc chính mình đã ngồi trong đó, thì không vào được.
    nut.disabled = r.you_in_room || (r.seat_white && r.seat_black);
    if (r.you_in_room) nut.textContent = "Vào lại";
    nut.addEventListener("click", () => vaoPhong(r.id));
    li.append(ma, trang, nut);
    el.roomList.appendChild(li);
  }
}

function closeSocket() {
  if (!socket) return;
  try { socket.close(); } catch { /* đang đóng rồi */ }
  socket = null;
}

function stopRoomPoll() {
  if (roomPollTimer) { clearInterval(roomPollTimer); roomPollTimer = null; }
}

function startRoomPoll() {
  stopRoomPoll();
  roomPollTimer = setInterval(async () => {
    if (!inRoom()) return;
    try {
      // `/state`, không phải `/api/rooms/{id}`: cần CẢ bàn cờ, không chỉ ghế.
      // Hỏi route kia thì WebSocket hỏng là bàn đứng yên vĩnh viễn.
      const du = await apiRoom(`/api/rooms/${room.id}/state`, "GET");
      room = du.room;
      if (du.game) applyRoomGame(du, !room.started);
      renderRoom();
    } catch (error) {
      say(error.message, true);
    }
  }, 1000);
}

function openSocket(roomId) {
  closeSocket();
  if (!playerToken) return;
  const ws = new WebSocket(
    `${location.origin.replace(/^http/, "ws")}/ws/room/${roomId}` +
    `?p=${encodeURIComponent(playerToken)}`
  );
  socket = ws;
  ws.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type !== "state" || !msg.data.room) return;
    room = msg.data.room;
    // Chưa bắt đầu thì chỉ vẽ bàn (thế xuất phát), GIỮ NGUYÊN màn phòng chờ.
    // `applyRoomGame` sẽ chuyển sang màn chơi nên không gọi ở đây.
    if (msg.data.room && !msg.data.room.started && msg.data.game) {
      // Phòng chờ: chỉ vẽ bàn (thế xuất phát), giữ nguyên màn chờ.
      applyRoomGame(msg.data, true);
    } else if (msg.data.room) {
      applyRoomGame(msg.data, false);
    }
    renderRoom();
  };
  ws.onopen = () => stopRoomPoll();
  ws.onclose = () => {
    socket = null;
    if (inRoom()) startRoomPoll();
  };
  ws.onerror = () => { /* onclose sẽ lo */ };
}

function applyRoomGame(data, giuManCho = false) {
  const g = data.game;
  // Ván đã bắt đầu: ẩn bảng phòng chờ và hiện bàn cờ. Thiếu dòng này thì
  // `view` kẹt ở "room" — bảng phòng chờ vẫn nằm trên bàn, và thông báo
  // "sai lượt" rơi vào nhánh dành cho đấu máy.
  showView(giuManCho ? "room" : "game");
  // Bàn xoay theo ghế của người chơi — nhưng CHỈ khi mới vào phòng. Đặt lại ở
  // mỗi lần đẩy thì nút "Lật bàn" không giữ được, và `buildSquares` xoá mất
  // highlight nên bàn không vẽ lại đúng.
  const doiGhe = data.room.you === "black" ? "b"
    : data.room.you === "white" ? "w" : orientation;
  if (doiGhe !== orientation) {
    orientation = doiGhe;
    buildSquares();
  }
  state = { ...g, human_color: data.room.you, elo: 0, thinking: false,
            is_room: true, started: data.room.started };
  selected = null;
  hidePicker();
  buildSquares();
  const cells = boardFromFen(state.fen);
  paintPieces(cells);
  paintBoard(cells);
  paintPanel();
  showInUrl(null);
  el.roomStatus.hidden = false;
  const ketNoi = data.room.opponent_connected !== false;
  if (!data.room.started) {
    // Chưa bắt đầu thì nói "Đến lượt bạn" là sai — còn chưa có lượt nào cả.
    el.roomStatus.textContent = "";
  } else if (state.over) {
    el.roomStatus.textContent = state.result_text;
  } else if (state.turn === data.room.you) {
    el.roomStatus.textContent = "Đến lượt bạn.";
  } else {
    el.roomStatus.textContent = ketNoi ? "Đến lượt đối thủ." : "Đối thủ đang mất kết nối.";
  }
  el.roomStatus.classList.toggle("warn", data.room.started && !state.over && !ketNoi);

  // C6: khi đối thủ mất kết nối thì cho phép kết thúc ván, nếu không một
  // người đóng tab là treo cả phòng — người còn lại không thể đầu hàng
  // (đó là thua) và host cũng chẳng làm được gì.
  el.forfeit.hidden = !(
    data.room.started && !state.over && !ketNoi && data.room.you_in_room
  );
  el.rematch.hidden = !(
    data.room.you_in_room && state.over && room && room.host_is_you
  );
  el.resign.hidden = !(data.room.started && !state.over && data.room.you_in_room);
}

async function vaoPhong(roomId) {
  try {
    room = await apiRoom(`/api/rooms/${roomId}/join`, "POST");
    const url = new URL(location.href);
    url.searchParams.set("room", roomId);
    url.searchParams.delete("g");
    history.replaceState(null, "", url);
    showView("room");
    renderRoom();
    openSocket(roomId);
  } catch (error) {
    say(error.message, true);
    if (view !== "home") showView("lobby");
    taiDanhSach();
  }
}

async function moPhong() {
  try {
    const { room_id } = await apiRoom("/api/rooms", "POST");
    await vaoPhong(room_id);
  } catch (error) {
    say(error.message, true);
  }
}

async function taiDanhSach() {
  try {
    renderLobby((await apiRoom("/api/rooms", "GET")).rooms);
  } catch (error) {
    say(error.message, true);
  }
}

async function guiNuocPhong(san) {
  if (busy) return;
  lockUi(true);
  try {
    const data = await apiRoom(`/api/rooms/${room.id}/move`, "POST", { san });
    say("");
    // Response của mình có thể đến SAU khi nước của đối thủ đã được đẩy.
    // Áp nó lúc đó là lùi bàn về trước nước của họ — và nếu nước đó là nước
    // cuối thì không còn gì đẩy nữa, hai bàn lệch vĩnh viễn.
    if (!state || data.game.moves.length >= state.moves.length) {
      applyRoomGame(data);
    }
  } catch (error) {
    say(error.message, true);   // bàn KHÔNG đổi
  } finally {
    lockUi(false);
  }
}

document.getElementById("tabs").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (!b) return;
  if (b.dataset.view === "lobby") { showView("lobby"); taiDanhSach(); return; }
  closeSocket();
  stopRoomPoll();
  room = null;
  showView("home");
});

document.getElementById("play-rooms").addEventListener("click", () => {
  showView("lobby");
  taiDanhSach();
});
document.getElementById("play-ai").addEventListener("click", () => {
  el.setup.hidden = false;
});
document.getElementById("play-both").addEventListener("click", async () => {
  try {
    const next = await api("/api/game", "POST");
    room = null;                  // rời phòng nếu đang ở trong một
    stopRoomPoll();
    closeSocket();
    showView("game");
    apply(next);                  // apply chạy SAU showView: nó chặn khi inRoom()
  } catch (error) {
    say(error.message, true);
  }
});

document.getElementById("make-room").addEventListener("click", moPhong);
document.getElementById("join-code").addEventListener("click", () => {
  const code = el.roomCode.value.trim().toLowerCase();
  if (code) vaoPhong(code);
});
document.getElementById("start-room").addEventListener("click", async () => {
  try {
    room = await apiRoom(`/api/rooms/${room.id}/start`, "POST");
    say("");
    renderRoom();
  } catch (error) {
    say(error.message, true);
  }
});
document.getElementById("copy-invite").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(el.invite.value);
    say("Đã sao chép link phòng.");
  } catch {
    el.invite.select();
    say("Không tự sao chép được — bạn copy ô link bên trên.");
  }
});
el.resign.addEventListener("click", async () => {
  if (!inRoom() || !state || !state.started || state.over) return;
  try {
    applyRoomGame(await apiRoom(`/api/rooms/${room.id}/resign`, "POST"));
  } catch (error) {
    say(error.message, true);
  }
});

el.leaveRoom.addEventListener("click", async () => {
  if (!inRoom() || !room) return;
  // Rời giữa ván là bỏ ván đi, nên hỏi lại một câu. Bấm nhầm mất cả ván.
  if (room.started && state && !state.over) {
    const ok = window.confirm(
      "Ván đang đánh dở. Rời phòng nghĩa là bỏ ván này — bạn chắc chứ?"
    );
    if (!ok) return;
  }
  lockUi(true);
  try {
    await apiRoom(`/api/rooms/${room.id}/leave`, "POST");
    closeSocket();
    stopRoomPoll();
    room = null;
    const url = new URL(location.href);
    url.searchParams.delete("room");
    history.replaceState(null, "", url);
    say("");
    showView("lobby");
    await taiDanhSach();
  } catch (error) {
    say(error.message, true);
  } finally {
    lockUi(false);
  }
});

el.rematch.addEventListener("click", async () => {
  if (!inRoom()) return;
  try {
    room = await apiRoom(`/api/rooms/${room.id}/rematch`, "POST");
    renderRoom();
  } catch (error) {
    say(error.message, true);
  }
});

el.forfeit.addEventListener("click", async () => {
  if (!inRoom()) return;
  try {
    applyRoomGame(await apiRoom(`/api/rooms/${room.id}/forfeit`, "POST"));
  } catch (error) {
    say(error.message, true);
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
  if (gameId) url.searchParams.set("g", gameId);
  else url.searchParams.delete("g");
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

const roomTrongUrl = new URLSearchParams(location.search).get("room");
if (roomTrongUrl) {
  showView("room");
  try {
    room = await apiRoom(`/api/rooms/${roomTrongUrl}`, "GET");
    await vaoPhong(roomTrongUrl);
  } catch (error) {
    say(error.message, true);
    showView("home");
  }
} else {
  showView("home");
  try {
    apply(await loadOrCreateGame());
  } catch (error) {
    say(error.message, true);
  }
}
