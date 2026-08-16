document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement;
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------------- Sticky nav blur ---------------- */
  const nav = document.getElementById("nav");
  if (nav) {
    const updateNavState = () => nav.classList.toggle("scrolled", window.scrollY > 40);
    window.addEventListener("scroll", updateNavState, { passive: true });
    updateNavState();
  }

  /* ---------------- Mobile menu ---------------- */
  const menuToggle = document.getElementById("menuToggle");
  const menuClose = document.getElementById("menuClose");
  const mobileMenu = document.getElementById("mobileMenu");

  if (menuToggle && menuClose && mobileMenu) {
    const openMenu = () => {
      mobileMenu.classList.add("open");
      menuToggle.setAttribute("aria-expanded", "true");
    };
    const closeMenu = () => {
      mobileMenu.classList.remove("open");
      menuToggle.setAttribute("aria-expanded", "false");
    };

    menuToggle.addEventListener("click", openMenu);
    menuClose.addEventListener("click", closeMenu);
    mobileMenu.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
  }

  /* ---------------- Bitcoin live ticker (only runs on pages with the chart) ---------------- */
  let drawChart = () => {};
  const canvas = document.getElementById("btcChart");

  if (canvas) {
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
      const prefix = chartState.mode === "live" ? "Live feed" : "Simulated data — live feed unavailable right now";
      btcUpdatedEl.textContent = `${prefix} · updated ${ago}`;
    };

    const setMode = (mode) => {
      chartState.mode = mode;
      chartState.lastUpdateAt = Date.now();
      liveBadge.classList.toggle("is-live", mode === "live");
      liveBadge.classList.toggle("is-demo", mode === "demo");
      liveLabel.textContent = mode === "live" ? "Live" : "Simulated";
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

    drawChart = function drawChart() {
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
      const pad = (max - min) * 0.18 || max * 0.01;
      const lo = min - pad;
      const hi = max + pad;
      const stepX = prices.length > 1 ? w / (prices.length - 1) : w;
      const toY = (price) => h - ((price - lo) / (hi - lo || 1)) * h;

      const isUp = prices[prices.length - 1] >= prices[0];
      const lineColor = getCssVar(isUp ? "--green" : "--red") || (isUp ? "#1e8e5a" : "#c0392b");

      const grad = ctx.createLinearGradient(0, 0, 0, h);
      grad.addColorStop(0, hexToRgba(lineColor, 0.25));
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
      ctx.lineWidth = 2.5;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.stroke();

      const lastX = (prices.length - 1) * stepX;
      const lastY = toY(prices[prices.length - 1]);
      ctx.beginPath();
      ctx.arc(lastX, lastY, 4.5, 0, Math.PI * 2);
      ctx.fillStyle = lineColor;
      ctx.fill();
    };

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

    const seedHistory = async () => {
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
    };

    const pollPrice = async () => {
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
    };

    (async () => {
      await seedHistory();
      await pollPrice();
      setInterval(pollPrice, POLL_MS);
    })();
  }

  /* ---------------- Theme toggle (shared across every page) ---------------- */
  const themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
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
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

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
  }

  /* ---------------- Skill rings (only present on the Skills page) ---------------- */
  const RING_R = 50;
  const RING_C = 2 * Math.PI * RING_R;

  document.querySelectorAll(".ring-progress").forEach((circle) => {
    circle.style.strokeDasharray = `${RING_C} ${RING_C}`;
    circle.style.strokeDashoffset = String(RING_C);
  });

  const animateRing = (card) => {
    const progress = card.querySelector(".ring-progress");
    const valueEl = card.querySelector(".ring-value");
    const level = parseFloat(progress.dataset.level);
    const target = parseFloat(valueEl.dataset.value);

    requestAnimationFrame(() => {
      progress.style.strokeDashoffset = String(RING_C - (RING_C * level) / 100);
    });

    if (prefersReducedMotion) {
      valueEl.textContent = `${target}%`;
      return;
    }

    const duration = 1300;
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      valueEl.textContent = `${Math.round(target * eased)}%`;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };

  /* ---------------- Scroll reveal (whatever .reveal sections exist on this page) ---------------- */
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          entry.target.querySelectorAll(".ring-card").forEach(animateRing);
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.2 }
  );

  document.querySelectorAll(".reveal").forEach((section) => observer.observe(section));

  /* ---------------- Copy email button (only present on the Contact page) ---------------- */
  const copyBtn = document.getElementById("copyEmailBtn");
  const toast = document.getElementById("toast");

  if (copyBtn && toast) {
    const copyLabel = document.getElementById("copyEmailLabel");
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
        copyLabel.textContent = "Copied!";
        showToast("Email copied to clipboard ✓");
        setTimeout(() => {
          copyLabel.textContent = original;
        }, 1800);
      } else {
        showToast(`Copy failed — email is ${email}`);
      }
    });
  }

  /* ---------------- Footer year (every page) ---------------- */
  document.querySelectorAll(".year").forEach((el) => {
    el.textContent = new Date().getFullYear();
  });
});
