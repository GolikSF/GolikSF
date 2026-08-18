(function () {
  const TOTAL_DAYS = 100;
  const START_DATE = new Date(2026, 7, 18); // Aug 18, 2026 (month is 0-indexed)
  const TARGET_DATE = new Date(START_DATE);
  TARGET_DATE.setDate(TARGET_DATE.getDate() + TOTAL_DAYS);

  const MS_PER_DAY = 24 * 60 * 60 * 1000;

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function getDaysLeft() {
    const now = startOfDay(new Date());
    const diff = Math.round((startOfDay(TARGET_DATE) - now) / MS_PER_DAY);
    return Math.max(0, Math.min(TOTAL_DAYS, diff));
  }

  function getDaysElapsed() {
    return TOTAL_DAYS - getDaysLeft();
  }

  function render() {
    const daysLeft = getDaysLeft();
    const daysElapsed = getDaysElapsed();

    const dayCountEl = document.getElementById("dayCount");
    const dayWordEl = document.getElementById("dayWord");
    const germanCountEl = document.getElementById("germanCount");

    dayCountEl.textContent = daysLeft;
    germanCountEl.textContent = daysLeft;

    if (daysLeft === 0) {
      dayWordEl.textContent = "SHE'S HOME!!! 🎉";
      launchConfetti();
    } else if (daysLeft === 1) {
      dayWordEl.textContent = "DAY LEFT!!!!!!";
    } else {
      dayWordEl.textContent = "DAYS!!!!!!";
    }

    buildGrid(daysElapsed);
    renderTargetDate();
  }

  function buildGrid(daysElapsed) {
    const grid = document.getElementById("grid");
    grid.innerHTML = "";
    for (let i = 0; i < TOTAL_DAYS; i++) {
      const tile = document.createElement("div");
      tile.className = "tile";
      tile.style.setProperty("--tile-img", "url('assets/yaara_tile.jpg')");
      tile.style.setProperty("--d", (i * 0.012) + "s");
      tile.title = "Day " + (i + 1);

      if (i < daysElapsed) {
        tile.classList.add("done");
      } else if (i === daysElapsed) {
        tile.classList.add("today");
      }
      grid.appendChild(tile);
    }
  }

  function renderTargetDate() {
    const el = document.getElementById("targetDate");
    const options = { year: "numeric", month: "long", day: "numeric" };
    el.textContent = "Freedom day: " + TARGET_DATE.toLocaleDateString(undefined, options);
  }

  function spawnFloaters() {
    const container = document.getElementById("floaters");
    const emojis = ["🇩🇪", "⛏️", "💙", "✨", "🪖"];
    const count = 16;
    for (let i = 0; i < count; i++) {
      const span = document.createElement("span");
      span.textContent = emojis[Math.floor(Math.random() * emojis.length)];
      span.style.left = Math.random() * 100 + "%";
      span.style.fontSize = 14 + Math.random() * 18 + "px";
      const duration = 14 + Math.random() * 12;
      span.style.animationDuration = duration + "s";
      span.style.animationDelay = -Math.random() * duration + "s";
      container.appendChild(span);
    }
  }

  function launchConfetti() {
    const layer = document.getElementById("confetti");
    if (layer.dataset.done) return;
    layer.dataset.done = "true";
    const colors = ["#2fa4ff", "#6fc3ff", "#ffffff", "#0f6fbf"];
    for (let i = 0; i < 80; i++) {
      const piece = document.createElement("div");
      piece.className = "confetti-piece";
      piece.style.left = Math.random() * 100 + "%";
      piece.style.background = colors[Math.floor(Math.random() * colors.length)];
      piece.style.animationDuration = 3 + Math.random() * 3 + "s";
      piece.style.animationDelay = Math.random() * 2 + "s";
      layer.appendChild(piece);
    }
  }

  spawnFloaters();
  render();

  // Keep it fresh if the page is left open across midnight.
  setInterval(render, 60 * 60 * 1000);
})();
