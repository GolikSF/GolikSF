document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- Mobile nav ---------------- */
  const navToggle = document.getElementById("navToggle");
  const navLinks = document.getElementById("navLinks");

  navToggle.addEventListener("click", () => {
    const isOpen = navLinks.classList.toggle("open");
    navToggle.classList.toggle("active", isOpen);
    navToggle.setAttribute("aria-expanded", String(isOpen));
  });

  navLinks.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navLinks.classList.remove("open");
      navToggle.classList.remove("active");
      navToggle.setAttribute("aria-expanded", "false");
    });
  });

  /* ---------------- Bitcoin live ticker ---------------- */
  const SIMPLE_PRICE_URL =
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true";
  const HISTORY_URL = "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=1";
  const MAX_POINTS = 48;
  const POLL_MS = 45000;
  const MOCK_SEED_PRICE = 65000;

  const btcPriceEl = document.getElementById("btcPrice");
  const btcChangeEl = document.getElementById("btcChange");
  const btcArrowEl = document.getElementById("btcArrow");
  const btcChangeValueEl = document.getElementById("btcChangeValue");
  const btcUpdatedEl = document.getElementById("btcUpdated");
  const liveBadge = document.getElementById("liveBadge");
  const liveLabel = document.getElementById("liveLabel");
  const canvas = document.getElementById("btcChart");
  const ctx = canvas.getContext("2d");

  const chartState = { points: [], lastUpdateAt: null, mode: "connecting" };

  const fetchJSON = async (url, timeoutMs) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } finally {
      clearTimeout(timer);
    }
  };

  const pushPoint = (price) => {
    chartState.points.push(price);
    if (chartState.points.length > MAX_POINTS) chartState.points.shift();
  };

  const nextMockPrice = () => {
    const last = chartState.points[chartState.points.length - 1] || MOCK_SEED_PRICE;
    const walk = last * (1 + (Math.random() - 0.5) * 0.006);
    return Math.max(1000, walk);
  };

  const seedMockHistory = () => {
    chartState.points = [];
    let price = MOCK_SEED_PRICE;
    for (let n = 0; n < 30; n += 1) {
      price *= 1 + (Math.random() - 0.5) * 0.01;
      chartState.points.push(price);
    }
  };

  const formatUsd = (value) =>
    `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const renderStats = (price, changePct) => {
    btcPriceEl.textContent = formatUsd(price);
    const up = changePct >= 0;
    btcChangeEl.classList.toggle("up", up);
    btcChangeEl.classList.toggle("down", !up);
    btcArrowEl.textContent = up ? "▲" : "▼";
    btcChangeValueEl.textContent = `${up ? "+" : ""}${changePct.toFixed(2)}%`;
  };

  const tickAgo = () => {
    if (!chartState.lastUpdateAt) return;
    const secs = Math.max(0, Math.round((Date.now() - chartState.lastUpdateAt) / 1000));
    const ago = secs < 2 ? "just now" : secs < 60 ? `${secs}s ago` : `${Math.round(secs / 60)}m ago`;
    const prefix =
      chartState.mode === "live" ? "Live feed" : "Demo data — live feed unavailable right now";
    btcUpdatedEl.textContent = `${prefix} · updated ${ago}`;
  };

  const setMode = (mode) => {
    chartState.mode = mode;
    chartState.lastUpdateAt = Date.now();
    liveBadge.classList.toggle("is-live", mode === "live");
    liveBadge.classList.toggle("is-demo", mode === "demo");
    liveLabel.textContent = mode === "live" ? "LIVE" : "DEMO DATA";
    tickAgo();
  };

  setInterval(tickAgo, 1000);

  const getCssVar = (name) => getComputedStyle(root).getPropertyValue(name).trim();

  const hexToRgba = (hex, alpha) => {
    const clean = hex.replace("#", "");
    const bigint = parseInt(clean, 16);
    const r = (bigint >> 16) & 255;
    const g = (bigint >> 8) & 255;
    const b = bigint & 255;
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  };

  function drawChart() {
    const prices = chartState.points;
    if (!prices.length) return;

    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const w = rect.width;
    const h = rect.height;
    ctx.clearRect(0, 0, w, h);

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const pad = (max - min) * 0.15 || max * 0.01;
    const lo = min - pad;
    const hi = max + pad;
    const stepX = prices.length > 1 ? w / (prices.length - 1) : w;
    const toY = (price) => h - ((price - lo) / (hi - lo || 1)) * h;

    const isUp = prices[prices.length - 1] >= prices[0];
    const lineColor = getCssVar(isUp ? "--green" : "--red") || (isUp ? "#33d17a" : "#ff5f56");

    const grad = ctx.createLinearGradient(0, 0, 0, h);
    grad.addColorStop(0, hexToRgba(lineColor, 0.3));
    grad.addColorStop(1, hexToRgba(lineColor, 0));

    ctx.beginPath();
    prices.forEach((p, i) => {
      const x = i * stepX;
      const y = toY(p);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo((prices.length - 1) * stepX, h);
    ctx.lineTo(0, h);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    prices.forEach((p, i) => {
      const x = i * stepX;
      const y = toY(p);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.stroke();

    const lastX = (prices.length - 1) * stepX;
    const lastY = toY(prices[prices.length - 1]);
    ctx.beginPath();
    ctx.arc(lastX, lastY, 4, 0, Math.PI * 2);
    ctx.fillStyle = lineColor;
    ctx.fill();
  }

  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawChart, 150);
  });

  const computeWindowChangePct = () => {
    const first = chartState.points[0];
    const last = chartState.points[chartState.points.length - 1];
    if (!first) return 0;
    return ((last - first) / first) * 100;
  };

  async function seedHistory() {
    try {
      const data = await fetchJSON(HISTORY_URL, 8000);
      const raw = data.prices || [];
      const step = Math.max(1, Math.floor(raw.length / MAX_POINTS));
      chartState.points = raw.filter((_, i) => i % step === 0).map((entry) => entry[1]);
      if (!chartState.points.length) throw new Error("empty history");
    } catch {
      seedMockHistory();
    }
    drawChart();
  }

  async function pollPrice() {
    try {
      const data = await fetchJSON(SIMPLE_PRICE_URL, 7000);
      const price = data.bitcoin.usd;
      const changePct = data.bitcoin.usd_24h_change;
      pushPoint(price);
      setMode("live");
      renderStats(price, changePct);
    } catch {
      const price = nextMockPrice();
      pushPoint(price);
      setMode("demo");
      renderStats(price, computeWindowChangePct());
    }
    drawChart();
  }

  /* ---------------- Theme toggle ---------------- */
  const themeToggle = document.getElementById("themeToggle");
  const store = {
    get() {
      try {
        return localStorage.getItem("theme");
      } catch {
        return null;
      }
    },
    set(value) {
      try {
        localStorage.setItem("theme", value);
      } catch {
        /* storage unavailable — theme just won't persist */
      }
    },
  };

  const effectiveTheme = () =>
    root.getAttribute("data-theme") ||
    (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");

  const applyTheme = (theme) => {
    root.setAttribute("data-theme", theme);
    themeToggle.textContent = theme === "dark" ? "☀" : "☾";
    drawChart();
  };

  applyTheme(store.get() || effectiveTheme());

  themeToggle.addEventListener("click", () => {
    const next = effectiveTheme() === "dark" ? "light" : "dark";
    applyTheme(next);
    store.set(next);
  });

  /* ---------------- Hero typing effect ---------------- */
  const typedName = document.getElementById("typedName");
  const heroCursor = document.getElementById("heroCursor");
  const fullName = "Golik SF";

  if (prefersReducedMotion) {
    typedName.textContent = fullName;
  } else {
    let i = 0;
    const type = () => {
      typedName.textContent = fullName.slice(0, i);
      i += 1;
      if (i <= fullName.length) {
        setTimeout(type, 90);
      } else {
        heroCursor.style.marginLeft = "2px";
      }
    };
    setTimeout(type, 400);
  }

  /* ---------------- Scroll reveal ---------------- */
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          entry.target.querySelectorAll(".skill-row").forEach((row) => row.classList.add("animate"));
          entry.target.querySelectorAll(".skill-value").forEach((el) => {
            el.textContent = el.dataset.value;
          });
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );

  document.querySelectorAll(".reveal").forEach((section) => observer.observe(section));

  /* ---------------- Copy email button ---------------- */
  const copyBtn = document.getElementById("copyEmailBtn");
  const copyLabel = document.getElementById("copyEmailLabel");
  const toast = document.getElementById("toast");
  let toastTimer;

  const showToast = (message) => {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2400);
  };

  copyBtn.addEventListener("click", async () => {
    const email = copyBtn.dataset.email;
    let copied = false;

    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(email);
        copied = true;
      }
    } catch {
      copied = false;
    }

    if (!copied) {
      try {
        const textarea = document.createElement("textarea");
        textarea.value = email;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        copied = document.execCommand("copy");
        document.body.removeChild(textarea);
      } catch {
        copied = false;
      }
    }

    if (copied) {
      const original = copyLabel.textContent;
      copyLabel.textContent = "copied!";
      showToast("Email copied to clipboard ✓");
      setTimeout(() => {
        copyLabel.textContent = original;
      }, 1800);
    } else {
      showToast(`Copy failed — email is ${email}`);
    }
  });

  /* ---------------- Back to top ---------------- */
  document.getElementById("backToTop").addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: prefersReducedMotion ? "auto" : "smooth" });
  });

  /* ---------------- Footer year ---------------- */
  document.getElementById("year").textContent = new Date().getFullYear();

  /* ---------------- Kick off the BTC feed ---------------- */
  (async () => {
    await seedHistory();
    await pollPrice();
    setInterval(pollPrice, POLL_MS);
  })();
});
