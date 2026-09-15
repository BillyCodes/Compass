/* =========================================================
   Compass — mock data layer
   ---------------------------------------------------------
   Everything in this file stands in for data that will
   eventually be served from Richshard's database via an API.
   Keeping it in one place means swapping mock data for real
   fetch() calls later only touches this file, not every page.
   ========================================================= */

const COMPASS_DATA = {

  // ---- Skills catalog -------------------------------------------------
  skills: [
    {
      id: "sql",
      name: "SQL & Relational Databases",
      category: "Database",
      description: "Designing schemas and writing queries that store and retrieve data efficiently.",
      courses: ["CSC 228 Data Structures & Algorithms", "CSC 310 Database Systems"],
      quote: "“Every interview I run has a SQL question. Students who can only recite syntax struggle — the ones who understand why we normalize data stand out.”",
      quoteRole: "Backend Engineer, mock professional insight",
    },
    {
      id: "version-control",
      name: "Git & Version Control",
      category: "Programming",
      description: "Tracking changes, branching, and collaborating on code without overwriting teammates' work.",
      courses: ["CSC 228 Data Structures & Algorithms", "CSC 340 Software Engineering"],
      quote: "“Nobody taught me how to resolve a merge conflict until my first internship. Learn it before you need it under pressure.”",
      quoteRole: "Software Engineer, mock professional insight",
    },
    {
      id: "system-design",
      name: "System & Software Architecture",
      category: "Software Engineering",
      description: "Structuring how the pieces of an application fit together so it can grow without falling apart.",
      courses: ["CSC 340 Software Engineering", "CSC 435 Computer Networks"],
      quote: "“Junior hires who can sketch how a request flows through a system — front end, API, database — ramp up twice as fast.”",
      quoteRole: "Software Architect, mock professional insight",
    },
    {
      id: "network-fundamentals",
      name: "Networking Fundamentals",
      category: "Software Engineering",
      description: "Understanding how systems talk to each other — protocols, latency, and failure points.",
      courses: ["CSC 435 Computer Networks"],
      quote: "“When production breaks at 2am, it's usually a networking issue. Comfort with the fundamentals is what separates a fast fix from a long night.”",
      quoteRole: "Site Reliability Engineer, mock professional insight",
    },
    {
      id: "auth-security",
      name: "Authentication & Access Control",
      category: "Cybersecurity",
      description: "Verifying who a user is and controlling what they're allowed to see or do.",
      courses: ["CSC 340 Software Engineering", "CSC 425 Digital Forensics"],
      quote: "“Students underestimate how much of security is just getting authentication right. It's the front door — get it wrong and nothing else matters.”",
      quoteRole: "Security Analyst, mock professional insight",
    },
    {
      id: "encryption",
      name: "Encryption & Data Protection",
      category: "Cybersecurity",
      description: "Protecting data at rest and in transit so a breach doesn't expose everything.",
      courses: ["CSC 425 Digital Forensics"],
      quote: "“We hire for people who ask ‘what happens if this leaks’ before they ship a feature, not after.”",
      quoteRole: "Cybersecurity Consultant, mock professional insight",
    },
    {
      id: "data-modeling",
      name: "Data Modeling",
      category: "Database",
      description: "Turning a messy real-world problem into a clean, well-structured set of tables and relationships.",
      courses: ["CSC 310 Database Systems", "CSC 228 Data Structures & Algorithms"],
      quote: "“A good data model prevents ninety percent of the bugs a bad one causes. It's the least glamorous skill and the most valuable.”",
      quoteRole: "Data Engineer, mock professional insight",
    },
    {
      id: "communication",
      name: "Technical Communication",
      category: "Professional Skills",
      description: "Explaining a technical decision clearly to teammates, managers, and non-technical stakeholders.",
      courses: ["CSC 340 Software Engineering"],
      quote: "“The best engineer on my team isn't the fastest coder — it's the one who can explain a tradeoff in two sentences.”",
      quoteRole: "Engineering Manager, mock professional insight",
    },
    {
      id: "testing-debugging",
      name: "Testing & Debugging",
      category: "Programming",
      description: "Proving code works, and methodically tracking down why it doesn't when it fails.",
      courses: ["CSC 228 Data Structures & Algorithms", "CSC 340 Software Engineering"],
      quote: "“We don't expect new grads to never write bugs. We expect them to debug systematically instead of guessing.”",
      quoteRole: "Software Engineer, mock professional insight",
    },
  ],

  // ---- Career pathways --------------------------------------------------
  pathways: [
    {
      id: "software-engineer",
      name: "Software Engineer",
      blurb: "Builds and maintains the applications people and businesses use every day.",
      skills: ["version-control", "system-design", "testing-debugging", "communication", "sql"],
      steps: [
        "Complete CSC 340 Software Engineering and build one project end-to-end (not just a class assignment).",
        "Contribute to a group repository on GitHub to practice real version-control workflows.",
        "Practice explaining a project's architecture out loud — this is what technical interviews actually test.",
      ],
    },
    {
      id: "database-analyst",
      name: "Database / Data Analyst",
      blurb: "Designs how data is stored and turns raw data into answers people can act on.",
      skills: ["sql", "data-modeling", "communication"],
      steps: [
        "Take CSC 310 Database Systems and rebuild a messy spreadsheet as a normalized schema.",
        "Practice writing SQL against a real, imperfect dataset — not a textbook one.",
        "Learn to present a data finding in one slide, not ten.",
      ],
    },
    {
      id: "cybersecurity-analyst",
      name: "Cybersecurity Analyst",
      blurb: "Finds and closes the gaps attackers would use, and responds when something goes wrong.",
      skills: ["auth-security", "encryption", "network-fundamentals"],
      steps: [
        "Take CSC 425 Digital Forensics and CSC 435 Computer Networks back to back — they reinforce each other.",
        "Set up authentication (OAuth/OpenID) on a personal project so it's not just theory.",
        "Follow a current CVE disclosure end-to-end to see how a real vulnerability gets found and patched.",
      ],
    },
    {
      id: "backend-developer",
      name: "Backend Developer",
      blurb: "Builds the server-side logic and APIs that power an application behind the scenes.",
      skills: ["system-design", "sql", "network-fundamentals", "version-control"],
      steps: [
        "Build a small API from scratch that reads and writes to a real database.",
        "Learn how HTTP requests actually travel — don't just call fetch() without knowing what happens next.",
        "Get comfortable reading someone else's codebase, not just writing your own.",
      ],
    },
  ],

  // ---- Professional insights (mock / placeholder content) ---------------
  // NOTE: these are sample entries only, written to show the format.
  // They will be replaced with real answers from the team's interviews.
  insights: [
    {
      role: "Software Engineer",
      industry: "Fintech",
      quote: "The gap isn't knowledge, it's judgment — knowing which of ten possible solutions is the right one for this problem, on this deadline.",
      tools: ["Git", "PostgreSQL", "CI/CD pipelines"],
      problems: ["Scaling a system as user load grows", "Keeping legacy code maintainable"],
    },
    {
      role: "Cybersecurity Analyst",
      industry: "Healthcare Technology",
      quote: "Come in already comfortable reading logs. Half of incident response is just knowing where to look first.",
      tools: ["SIEM platforms", "TLS/PKI", "Access-control frameworks"],
      problems: ["Balancing usability against strict compliance requirements", "Phishing and social engineering attempts"],
    },
    {
      role: "Data Analyst",
      industry: "Retail / E-commerce",
      quote: "Every dataset I've been handed as a new hire was messier than anything in a classroom. Get comfortable with that mess early.",
      tools: ["SQL", "Python (pandas)", "BI dashboards"],
      problems: ["Reconciling data from multiple inconsistent sources", "Explaining statistical nuance to non-technical stakeholders"],
    },
    {
      role: "Engineering Manager",
      industry: "SaaS / Enterprise Software",
      quote: "I can teach a new grad a framework in a week. I can't teach them to ask for help before they've burned three days stuck.",
      tools: ["Project tracking tools", "Code review workflows"],
      problems: ["Onboarding new engineers quickly", "Balancing technical debt against new feature requests"],
    },
  ],

  // ---- Sample student dashboard (mock persona) ---------------------------
  sampleStudent: {
    name: "Jordan A.",
    initials: "JA",
    major: "Computer Science",
    standing: "Senior",
    skillProgress: [
      { skill: "SQL & Relational Databases", level: 80 },
      { skill: "Git & Version Control", level: 65 },
      { skill: "System & Software Architecture", level: 45 },
      { skill: "Authentication & Access Control", level: 30 },
    ],
    courses: [
      { code: "CSC 228", name: "Data Structures & Algorithms", status: "Completed" },
      { code: "CSC 310", name: "Database Systems", status: "In Progress" },
      { code: "CSC 340", name: "Software Engineering", status: "Planned" },
      { code: "CSC 425", name: "Digital Forensics", status: "Planned" },
    ],
    roadmap: [
      "Finish CSC 310 and apply it by rebuilding a personal project's data storage as a real schema.",
      "Start a small project using OAuth so Authentication & Access Control isn't purely theoretical.",
      "Read one professional insight per week in the Insights hub and note one takeaway.",
    ],
  },
};
