# Compass — Digital Corsairs Senior Project

A front-end prototype of Compass: a platform that helps Jackson State students see which skills matter, how their coursework builds them, and what industry professionals want new grads to know.

## Status

This is a **static, front-end-only prototype**. There is no backend or database wired up yet — all content lives in `js/data.js` as mock data so the team can review layout and flow before Richshard's database is connected.

## Structure

```
compass-site/
├── index.html          Home / landing page
├── skills.html          Skill Explorer — filterable skill catalog
├── pathways.html         Career Pathways — pick a path, see required skills + next steps
├── insights.html         Professional Insights — cards from industry professionals (sample content)
├── dashboard.html        Student Dashboard — sample logged-in-student preview
├── about.html            Objective, research questions, and the team
├── css/style.css         Shared styling (Compass navy/gold theme)
├── js/data.js            Mock data — skills, pathways, insights, sample student
└── js/main.js            Renders data.js into each page + nav behavior
```

## Notes for the team

- **All content is mock data** in `js/data.js`. The Insights page is explicitly marked "sample content" since it will be replaced by real answers from our planned interviews.
- **No backend yet.** When Richshard's database and an API are ready, the plan is to swap the static `COMPASS_DATA` object in `data.js` for `fetch()` calls — the page rendering code in `main.js` shouldn't need to change much.
- **AI is a planned feature, not built yet** — flagged on the home page as "Planned" so it isn't confused with something that already works.
- **Cybersecurity isn't implemented here** — there's no login or real student data yet, so there's nothing to secure. Once accounts and real data are added, that's where Kershad's authentication/encryption work plugs in.

## Running it locally

No build step — it's plain HTML/CSS/JS. Easiest ways to view it:

1. Open `index.html` directly in a browser, or
2. In VS Code, use the "Live Server" extension and click "Go Live" on `index.html` (recommended — keeps relative links and any future `fetch()` calls working correctly).
