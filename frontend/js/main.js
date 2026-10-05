/* =========================================================
   Compass — shared interactivity
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
  initNavToggle();
  initSkillsPage();
  initPathwaysPage();
  initInsightsPage();
  initDashboardPage();
});

// ---------- Mobile nav ----------
function initNavToggle() {
  const toggle = document.querySelector(".nav-toggle");
  const links = document.querySelector(".nav-links");
  if (!toggle || !links) return;
  toggle.addEventListener("click", () => links.classList.toggle("open"));
}

// ---------- Skills page ----------
function initSkillsPage() {
  const grid = document.getElementById("skills-grid");
  if (!grid) return;

  const skills = COMPASS_DATA.skills;
  const categories = ["All", ...new Set(skills.map((s) => s.category))];

  const filterBar = document.getElementById("skills-filter");
  filterBar.innerHTML = categories
    .map((c, i) => `<button class="chip${i === 0 ? " active" : ""}" data-cat="${c}">${c}</button>`)
    .join("");

  function render(activeCat) {
    const list = activeCat === "All" ? skills : skills.filter((s) => s.category === activeCat);
    grid.innerHTML = list
      .map(
        (s) => `
        <div class="card skill-card">
          <span class="tag">${s.category}</span>
          <h3>${s.name}</h3>
          <p>${s.description}</p>
          <div class="meta-label">Built by these JSU courses</div>
          <div>${s.courses.map((c) => `<span class="tag gold">${c}</span>`).join("")}</div>
          <div class="quote">${s.quote}<br><span style="font-style:normal; font-size:0.8rem; color:var(--mute);">— ${s.quoteRole}</span></div>
        </div>`
      )
      .join("");
  }

  filterBar.addEventListener("click", (e) => {
    const btn = e.target.closest(".chip");
    if (!btn) return;
    filterBar.querySelectorAll(".chip").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    render(btn.dataset.cat);
  });

  render("All");
}

// ---------- Pathways page ----------
function initPathwaysPage() {
  const selectBar = document.getElementById("pathway-select");
  const panel = document.getElementById("pathway-panel");
  if (!selectBar || !panel) return;

  const pathways = COMPASS_DATA.pathways;
  const skillsById = Object.fromEntries(COMPASS_DATA.skills.map((s) => [s.id, s]));

  selectBar.innerHTML = pathways
    .map(
      (p, i) => `
      <button class="pathway-btn${i === 0 ? " active" : ""}" data-id="${p.id}">
        ${p.name}
        <span>${p.blurb}</span>
      </button>`
    )
    .join("");

  function render(id) {
    const p = pathways.find((x) => x.id === id);
    panel.innerHTML = `
      <h3>${p.name}</h3>
      <p style="color:var(--mute); max-width:640px;">${p.blurb}</p>
      <div class="meta-label" style="font-size:0.75rem; font-weight:700; color:var(--mute); letter-spacing:0.5px; margin:20px 0 10px;">Core skills for this path</div>
      <ul class="skill-list">
        ${p.skills.map((sid) => `<li><span class="dot"></span>${skillsById[sid] ? skillsById[sid].name : sid}</li>`).join("")}
      </ul>
      <div class="meta-label" style="font-size:0.75rem; font-weight:700; color:var(--mute); letter-spacing:0.5px; margin:24px 0 4px;">Recommended next steps</div>
      <ol class="step-list">
        ${p.steps.map((s) => `<li>${s}</li>`).join("")}
      </ol>
    `;
  }

  selectBar.addEventListener("click", (e) => {
    const btn = e.target.closest(".pathway-btn");
    if (!btn) return;
    selectBar.querySelectorAll(".pathway-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    render(btn.dataset.id);
  });

  render(pathways[0].id);
}

// ---------- Insights page ----------
function initInsightsPage() {
  const grid = document.getElementById("insights-grid");
  if (!grid) return;

  grid.innerHTML = COMPASS_DATA.insights
    .map(
      (ins) => `
      <div class="card insight-card">
        <div class="role">${ins.role}</div>
        <div class="industry">${ins.industry}</div>
        <p class="pull-quote">${ins.quote}</p>
        <div class="meta-label">Tools they rely on</div>
        <div style="margin-bottom:14px;">${ins.tools.map((t) => `<span class="tag">${t}</span>`).join("")}</div>
        <div class="meta-label" style="margin-top:0;">Problems they're solving right now</div>
        <div>${ins.problems.map((p) => `<span class="tag gold">${p}</span>`).join("")}</div>
      </div>`
    )
    .join("");
}

// ---------- Dashboard page ----------
function initDashboardPage() {
  const root = document.getElementById("dashboard-root");
  if (!root) return;

  const s = COMPASS_DATA.sampleStudent;

  document.getElementById("dash-initials").textContent = s.initials;
  document.getElementById("dash-name").textContent = s.name;
  document.getElementById("dash-meta").textContent = `${s.major} · ${s.standing}`;

  const progressEl = document.getElementById("dash-progress");
  progressEl.innerHTML = s.skillProgress
    .map(
      (p) => `
      <div class="progress-row">
        <div class="row-label"><span>${p.skill}</span><span>${p.level}%</span></div>
        <div class="progress-track"><div class="progress-fill" style="width:${p.level}%"></div></div>
      </div>`
    )
    .join("");

  const courseEl = document.getElementById("dash-courses");
  courseEl.innerHTML = s.courses
    .map(
      (c) => `<li><span><span class="course-code">${c.code}</span>${c.name}</span><span class="tag${c.status === "Completed" ? " gold" : ""}">${c.status}</span></li>`
    )
    .join("");

  const roadmapEl = document.getElementById("dash-roadmap");
  roadmapEl.innerHTML = s.roadmap.map((r) => `<li>${r}</li>`).join("");
}
