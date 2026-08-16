document.addEventListener("DOMContentLoaded", () => {
  // ---- Mobile nav toggle ----
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

  // ---- Dark mode toggle ----
  const themeToggle = document.getElementById("themeToggle");
  const root = document.documentElement;
  const storedTheme = localStorage.getItem("theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;

  const applyTheme = (theme) => {
    if (theme === "dark") {
      root.setAttribute("data-theme", "dark");
      themeToggle.textContent = "☀️";
    } else {
      root.removeAttribute("data-theme");
      themeToggle.textContent = "🌙";
    }
  };

  applyTheme(storedTheme || (prefersDark ? "dark" : "light"));

  themeToggle.addEventListener("click", () => {
    const isDark = root.getAttribute("data-theme") === "dark";
    const next = isDark ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("theme", next);
  });

  // ---- Reveal sections + animate skill bars on scroll ----
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          entry.target
            .querySelectorAll(".skill-card")
            .forEach((card) => card.classList.add("animate"));
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15 }
  );

  document.querySelectorAll(".reveal").forEach((section) => observer.observe(section));

  // ---- Back to top button ----
  const backToTop = document.getElementById("backToTop");
  backToTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  // ---- Footer year ----
  document.getElementById("year").textContent = new Date().getFullYear();
});
