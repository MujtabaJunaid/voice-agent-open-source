const watchBtn = document.getElementById("watchBtn");
const callLabel = document.getElementById("callLabel");
const statusEl = document.getElementById("status");
const thread = document.getElementById("thread");
const bookingEl = document.getElementById("booking");
const bookingDetailsEl = document.getElementById("bookingDetails");

let room = null;
let watching = false;

function addBubble(speaker, text) {
  const div = document.createElement("div");
  const mine = speaker === "My Assistant";
  div.className = `bubble bubble--${mine ? "mine" : "aria"}`;
  div.innerHTML = `<span class="bubble__speaker">${speaker}</span>${text}`;
  thread.appendChild(div);
  thread.scrollTop = thread.scrollHeight;
}

function showBooking(b) {
  bookingDetailsEl.textContent = `${b.patient_name} · ${b.date} ${b.time} · ${b.reason}`;
  bookingEl.hidden = false;
}

async function startWatching() {
  statusEl.textContent = "connecting…";
  const res = await fetch("/api/token");
  const { token, url } = await res.json();

  room = new LivekitClient.Room();

  room.on(LivekitClient.RoomEvent.DataReceived, (payload) => {
    try {
      const msg = JSON.parse(new TextDecoder().decode(payload));
      if (msg.type === "line") addBubble(msg.speaker, msg.text);
      if (msg.type === "booking") showBooking(msg);
    } catch (_) {
      /* ignore non-JSON data */
    }
  });

  room.on(LivekitClient.RoomEvent.ParticipantConnected, (p) => {
    statusEl.textContent = `${p.name || p.identity} joined the call`;
  });

  room.on(LivekitClient.RoomEvent.Disconnected, () => {
    watching = false;
    watchBtn.classList.remove("active");
    callLabel.textContent = "Watch call";
    statusEl.textContent = "disconnected";
  });

  await room.connect(url, token);

  watching = true;
  watchBtn.classList.add("active");
  callLabel.textContent = "Stop watching";
  statusEl.textContent = "watching the room";
}

async function stopWatching() {
  if (room) await room.disconnect();
  room = null;
}

watchBtn.addEventListener("click", () => {
  if (watching) {
    stopWatching();
  } else {
    startWatching().catch((err) => {
      console.error(err);
      statusEl.textContent = "connection failed — check console";
    });
  }
});

// Fill in anything already booked before this page connected.
fetch("/api/appointments")
  .then((r) => r.json())
  .then((rows) => {
    if (rows.length) showBooking(rows[0]);
  })
  .catch(() => {});
