"""
Seed the development database with SYNTHETIC data (blueprint §6.2, §12.1).

    python manage.py seed_compass            # idempotent: updates reference data, keeps students
    python manage.py seed_compass --reset    # also deletes and recreates the demo accounts

Demo accounts (development only — never reuse these passwords anywhere real):
    student.a@compass.test   CompassDemo-A1   Student A (has skills, courses, history)
    student.b@compass.test   CompassDemo-B2   Student B (used for cross-account tests)
    disabled@compass.test    CompassDemo-X9   disabled account (login must fail)

All companies, professionals and postings are fictional pilot content.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    Account,
    CareerProfile,
    CareerRequirement,
    CourseSkill,
    FieldNote,
    JobPosting,
    MatchResult,
    PostingRequirement,
    ProgressSnapshot,
    Skill,
    Student,
    StudentCourse,
    StudentSkill,
    UniversityCourse,
)
from core.services import comparison, skillprint

# skill_id, name, category, aliases, description, why it matters
SKILLS = [
    # Programming
    ("python", "Python", "programming", "python3", "General-purpose language for scripting, back ends, data and automation.", "The most requested language in entry-level postings across cloud, data and security."),
    ("java", "Java", "programming", "", "Object-oriented language behind many enterprise systems and Android.", "Common in large-company back ends and most CS curricula."),
    ("javascript", "JavaScript", "programming", "JS, ES6, TypeScript, Node.js, NodeJS, React", "Language of the web front end and Node.js services.", "Every web product touches it; full-stack roles expect it."),
    ("cpp", "C++", "programming", "C/C++", "Systems language for performance-critical software.", "Shows you understand memory and performance."),
    ("git", "Git & Version Control", "programming", "Git, GitHub, GitLab, version control, pull request, pull requests", "Tracking changes, branching, and collaborating on code without overwriting work.", "Used on every professional software team, every day."),
    ("data-structures", "Data Structures & Algorithms", "programming", "data structures, algorithms, algorithm design, Big-O, big O", "Choosing the right structure and algorithm for a problem and reasoning about cost.", "The core of technical interviews and of code that scales."),
    ("testing", "Software Testing", "programming", "unit testing, unit tests, pytest, JUnit, test-driven, TDD, automated testing, QA", "Writing automated tests that prove code behaves as intended.", "Teams trust and ship code that is tested."),
    ("rest-apis", "REST APIs", "programming", "REST, RESTful, REST API, API design, Flask, Django, FastAPI, Express", "Designing and building HTTP APIs that other software calls.", "How almost every modern service talks to another."),
    # Data
    ("sql", "SQL & Relational Databases", "data", "SQL, PostgreSQL, Postgres, MySQL, SQL Server, relational database, relational databases, SQLite", "Designing schemas and writing queries that store and retrieve data efficiently.", "Data lives in databases; nearly every technical role queries one."),
    ("data-modeling", "Data Modeling", "data", "ERD, entity relationship, schema design, normalization, data model", "Structuring entities, keys and relationships so data stays correct.", "Bad models cause bugs no code can fix later."),
    ("data-analysis", "Data Analysis", "data", "pandas, NumPy, data analysis, analytics, Excel, Tableau, Power BI", "Cleaning, exploring and summarizing data to answer questions.", "Turns raw records into decisions."),
    ("machine-learning", "Machine Learning", "data", "machine learning, ML, scikit-learn, TensorFlow, PyTorch", "Training models that learn patterns from data.", "Growing in nearly every industry; strong differentiator."),
    # Systems
    ("linux", "Linux", "systems", "Linux, Ubuntu, Bash, shell scripting, command line, Unix", "Working on the command line, managing processes, files and permissions.", "Servers, containers and cloud machines overwhelmingly run Linux."),
    ("networking", "Networking Fundamentals", "systems", "TCP/IP, networking, DNS, HTTP, subnetting, routing, OSI", "How data moves between machines: IP, TCP, DNS, HTTP and routing.", "Cloud, security and back-end debugging all depend on it."),
    ("system-design", "System & Software Architecture", "systems", "system design, software architecture, microservices, distributed systems, scalability", "Structuring how the pieces of an application fit together so it can grow.", "Separates engineers who can build features from those who can build systems."),
    ("os", "Operating Systems", "systems", "operating systems, processes, threads, concurrency, memory management", "Processes, threads, memory and scheduling.", "Explains why software behaves the way it does under load."),
    # Cloud / tools
    ("aws", "AWS Services", "cloud", "AWS, Amazon Web Services, EC2, S3, Lambda, IAM, CloudFormation", "Core Amazon Web Services compute, storage and identity services.", "The most widely used public cloud."),
    ("azure", "Microsoft Azure", "cloud", "Azure", "Microsoft's cloud platform.", "Common in enterprise and government environments."),
    ("docker", "Docker & Containers", "cloud", "Docker, containers, containerization, Dockerfile", "Packaging applications with their dependencies so they run the same everywhere.", "The standard way software is shipped today."),
    ("kubernetes", "Kubernetes", "cloud", "Kubernetes, K8s, EKS, AKS, GKE, Helm", "Running and scaling containers across many machines.", "Runs most large production container workloads."),
    ("iac", "Infrastructure as Code", "cloud", "Terraform, infrastructure as code, IaC, Ansible, CloudFormation, Pulumi", "Defining servers and networks in versioned code instead of clicking consoles.", "Makes infrastructure repeatable and reviewable."),
    ("cicd", "CI/CD", "cloud", "CI/CD, continuous integration, continuous delivery, continuous deployment, GitHub Actions, Jenkins, pipelines", "Automatically building, testing and deploying every change.", "How teams ship safely many times a day."),
    ("monitoring", "Monitoring & Logging", "cloud", "monitoring, logging, observability, CloudWatch, Prometheus, Grafana, Splunk, Datadog", "Watching systems in production and finding problems from logs and metrics.", "You can't fix what you can't see."),
    # Security
    ("security-fundamentals", "Security Fundamentals", "security", "cybersecurity, information security, CIA triad, least privilege, threat modeling, security fundamentals", "Confidentiality, integrity, availability, least privilege and threat thinking.", "Every engineer is now expected to build securely."),
    ("auth", "Authentication & Access Control", "security", "authentication, authorization, access control, OAuth, OIDC, SSO, MFA, RBAC", "Proving who a user is and controlling what they can do.", "The most common source of serious breaches when done wrong."),
    ("cloud-security", "Cloud Security", "security", "cloud security, IAM policies, security groups, KMS, encryption at rest", "Securing identities, networks and data in cloud environments.", "Misconfigured cloud resources are a leading cause of data exposure."),
    ("secure-coding", "Secure Coding", "security", "secure coding, OWASP, SQL injection, XSS, input validation, OWASP Top 10", "Writing code that resists injection, XSS and other common attacks.", "Stops vulnerabilities before they ship."),
    ("incident-response", "Incident Response", "security", "incident response, SIEM, SOC, threat detection, forensics, vulnerability management", "Detecting, investigating and recovering from security events.", "Core work of security analyst and SOC roles."),
    # Professional
    ("communication", "Technical Communication", "professional", "communication, technical writing, documentation, presentations, presenting, written and verbal", "Explaining technical ideas and tradeoffs clearly, in writing and out loud.", "Professionals rank it among the most underrated engineering skills."),
    ("teamwork", "Collaboration & Teamwork", "professional", "teamwork, collaboration, cross-functional, collaborative, team player", "Working effectively with others on shared goals.", "Software is built by teams."),
    ("agile", "Agile & Scrum", "professional", "Agile, Scrum, sprint, sprints, Kanban, Jira", "Planning and delivering work in short, reviewable iterations.", "How most software teams organize their work."),
    ("problem-solving", "Problem Solving", "professional", "problem solving, problem-solving, troubleshooting, debugging, analytical", "Breaking down unfamiliar problems and debugging systematically.", "The skill every interviewer is really testing."),
]

# Sample course catalog (illustrative codes for the pilot)
COURSES = [
    ("csc119", "CSC 119", "Introduction to Programming", [("python", 2), ("problem-solving", 2)]),
    ("csc216", "CSC 216", "Object-Oriented Programming", [("java", 3), ("git", 2), ("testing", 2)]),
    ("csc228", "CSC 228", "Data Structures & Algorithms", [("data-structures", 3), ("cpp", 2), ("problem-solving", 3)]),
    ("csc312", "CSC 312", "Database Systems", [("sql", 3), ("data-modeling", 3)]),
    ("csc323", "CSC 323", "Operating Systems", [("os", 3), ("linux", 2)]),
    ("csc325", "CSC 325", "Software Engineering", [("git", 3), ("agile", 3), ("teamwork", 3), ("testing", 2), ("system-design", 2)]),
    ("csc350", "CSC 350", "Algorithms Analysis & Design", [("data-structures", 4)]),
    ("csc435", "CSC 435", "Computer Networks", [("networking", 3), ("linux", 2)]),
    ("csc440", "CSC 440", "Introduction to Cybersecurity", [("security-fundamentals", 3), ("auth", 2), ("secure-coding", 2)]),
    ("csc445", "CSC 445", "Cloud Computing", [("aws", 2), ("docker", 2), ("cloud-security", 2)]),
    ("csc450", "CSC 450", "Senior Project", [("communication", 3), ("teamwork", 3), ("rest-apis", 2), ("system-design", 2)]),
    ("csc460", "CSC 460", "Data Science Foundations", [("data-analysis", 3), ("machine-learning", 2), ("python", 3)]),
]

# slug, title, summary, [(skill, level, weight, mandatory)]
CAREERS = [
    ("cloud-engineer", "Cloud Engineer", "Builds and runs the infrastructure applications live on: compute, networks, containers, automation and monitoring in the cloud.",
     [("linux", 3, 3, True), ("networking", 3, 3, True), ("aws", 3, 3, True), ("python", 3, 2, False), ("docker", 3, 2, False),
      ("iac", 3, 2, False), ("cicd", 2, 1, False), ("monitoring", 2, 1, False), ("cloud-security", 2, 2, False), ("communication", 3, 1, False)]),
    ("software-engineer", "Software Engineer", "Designs, builds and tests application features, APIs and services as part of a product team.",
     [("data-structures", 3, 3, True), ("git", 3, 2, True), ("python", 3, 2, False), ("java", 3, 2, False), ("rest-apis", 3, 2, False),
      ("sql", 3, 2, False), ("testing", 3, 2, False), ("system-design", 2, 1, False), ("agile", 2, 1, False), ("communication", 3, 2, False)]),
    ("security-analyst", "Security Analyst", "Monitors, investigates and responds to security events, and helps teams fix the weaknesses behind them.",
     [("security-fundamentals", 3, 3, True), ("networking", 3, 3, True), ("linux", 3, 2, False), ("incident-response", 3, 3, True),
      ("auth", 3, 2, False), ("monitoring", 3, 2, False), ("python", 2, 1, False), ("cloud-security", 2, 1, False), ("communication", 3, 2, False)]),
    ("data-analyst", "Data Analyst", "Turns raw data into answers: querying, cleaning, analyzing and presenting findings to decision makers.",
     [("sql", 3, 3, True), ("data-analysis", 3, 3, True), ("python", 3, 2, False), ("data-modeling", 2, 1, False),
      ("machine-learning", 2, 1, False), ("communication", 3, 2, True), ("problem-solving", 3, 1, False)]),
]

POSTINGS = [
    {
        "title": "Associate Cloud Engineer",
        "company": "Northwind Cloud (fictional)",
        "location": "Remote · Multiple locations",
        "tags": "Cloud, Infrastructure, DevOps",
        "reqs": [("linux", 3, 2, True), ("python", 3, 2, True), ("networking", 3, 2, True), ("communication", 3, 1, True),
                 ("aws", 3, 2, False), ("iac", 3, 1, False), ("system-design", 2, 1, False), ("monitoring", 2, 1, False),
                 ("kubernetes", 2, 1, False), ("cicd", 2, 1, False)],
        "description": "Join a platform team that runs customer workloads on AWS.\n\nRequirements\n- Linux administration\n- Python scripting\n- Networking fundamentals (DNS, TCP/IP)\n- Clear technical communication\n\nPreferred\n- AWS services (EC2, S3, IAM)\n- Terraform or other infrastructure as code\n- Kubernetes, CI/CD pipelines, monitoring with CloudWatch",
    },
    {
        "title": "Software Engineer Intern",
        "company": "Magnolia Health Systems (fictional)",
        "location": "Jackson, MS · Hybrid",
        "tags": "Software, Web, Internship",
        "reqs": [("data-structures", 3, 2, True), ("git", 2, 2, True), ("python", 3, 2, False), ("javascript", 2, 1, False),
                 ("rest-apis", 2, 1, False), ("sql", 2, 1, False), ("testing", 2, 1, False), ("teamwork", 3, 1, False)],
        "description": "Build features for a patient-scheduling web app.\n\nRequirements\n- Data structures and algorithms coursework\n- Git and pull requests\n\nNice to have\n- Python or JavaScript, REST APIs, SQL, unit testing, collaboration",
    },
    {
        "title": "SOC Analyst I",
        "company": "Riverbend Bank (fictional)",
        "location": "Memphis, TN · On-site",
        "tags": "Security, SOC",
        "reqs": [("security-fundamentals", 3, 2, True), ("networking", 3, 2, True), ("incident-response", 2, 2, True),
                 ("linux", 2, 1, False), ("monitoring", 2, 1, False), ("auth", 2, 1, False), ("communication", 3, 1, False)],
        "description": "Monitor alerts and investigate incidents in a 24/7 security operations center.\n\nRequirements\n- Security fundamentals\n- TCP/IP networking\n- Incident response or SIEM exposure\n\nPreferred\n- Linux, Splunk monitoring, access control, written communication",
    },
    {
        "title": "Junior Data Analyst",
        "company": "Pelican Labs (fictional)",
        "location": "New Orleans, LA · Hybrid",
        "tags": "Data, Analytics",
        "reqs": [("sql", 3, 2, True), ("data-analysis", 3, 2, True), ("python", 2, 1, False), ("communication", 3, 1, True),
                 ("machine-learning", 2, 1, False)],
        "description": "Help product teams answer questions with data.\n\nRequirements\n- SQL\n- Data analysis with Excel or pandas\n- Presenting findings\n\nBonus\n- Python, machine learning",
    },
]

FIELD_NOTES = [
    {
        "author_name": "Marcus Hale", "author_role": "Cloud Infrastructure Engineer", "author_org": "Northwind Cloud (fictional)", "years": 7,
        "headline": "Linux and networking are the job; the cloud console is just the dashboard.",
        "quote": "Students underestimate how important Linux and networking are. Those fundamentals will make you dangerous in any cloud role.",
        "body": "Most incidents I work aren't 'AWS problems.' They're a misconfigured security group, a DNS record that didn't propagate, or a disk that filled up on a Linux host. The engineers who ramp fastest can SSH into a box, read logs, and reason about packets.",
        "working_on": "Moving our deployment pipeline from hand-run scripts to Terraform and GitHub Actions, so every environment is built the same way and reviewed like code.",
        "learn_next": "Get comfortable on the Linux command line, learn how DNS and TCP actually work, then write one small Terraform project that builds a VM and a network.",
        "skills": ["linux", "networking", "aws", "iac", "cicd"], "days_ago": 3,
    },
    {
        "author_name": "Priya Nandakumar", "author_role": "Software Engineer", "author_org": "Magnolia Health Systems (fictional)", "years": 5,
        "headline": "The best engineers can explain a tradeoff in two sentences.",
        "quote": "The best engineers I work with can explain a tradeoff clearly. Technical communication is a real skill.",
        "body": "Code review is where you grow fastest. When you open a pull request, write what changed, why, and what you weren't sure about. That habit alone makes you easier to work with than most new hires.",
        "working_on": "Splitting a large scheduling service into smaller APIs, with contract tests so one team's change can't silently break another's.",
        "learn_next": "Write tests for your class projects, practice writing pull-request descriptions, and read one system-design case study a week.",
        "skills": ["communication", "system-design", "testing", "git", "rest-apis"], "days_ago": 6,
    },
    {
        "author_name": "Denise Carter", "author_role": "Security Operations Lead", "author_org": "Riverbend Bank (fictional)", "years": 11,
        "headline": "Learn what normal looks like before you hunt for abnormal.",
        "quote": "You can't spot an attack in the logs until you know what a normal Tuesday looks like on the network.",
        "body": "New analysts want to jump to malware analysis. The ones who succeed first learn how authentication, DNS and web traffic look on a healthy day. Then anomalies jump out.",
        "working_on": "Tuning our SIEM rules to cut false-positive alerts, and adding phishing-resistant MFA for every employee account.",
        "learn_next": "Build a home lab, collect logs from a Linux VM, and practice writing one detection for failed logins.",
        "skills": ["incident-response", "monitoring", "auth", "networking", "security-fundamentals"], "days_ago": 9,
    },
    {
        "author_name": "Andre Washington", "author_role": "Data Analyst", "author_org": "Pelican Labs (fictional)", "years": 4,
        "headline": "SQL first. Fancy models later.",
        "quote": "Ninety percent of my week is SQL and a clear chart. Get great at those before you reach for machine learning.",
        "body": "Stakeholders don't care which library you used. They care whether the number is right and whether they understand the chart. A clean query and a one-sentence takeaway beat a complicated model nobody trusts.",
        "working_on": "Rebuilding our weekly product dashboard so every metric has a written definition and a tested query behind it.",
        "learn_next": "Practice joins and window functions on a real dataset, then present one finding to a friend in under two minutes.",
        "skills": ["sql", "data-analysis", "communication", "data-modeling"], "days_ago": 12,
    },
    {
        "author_name": "Keisha Brown", "author_role": "Platform Engineer", "author_org": "Delta Freight Tech (fictional)", "years": 6,
        "headline": "Containers are where software and infrastructure meet.",
        "quote": "If you can write a Dockerfile, run it locally, and explain why it works in production too, you're ahead of most applicants.",
        "body": "We hire people who can close the loop: write the code, containerize it, and see it run. Kubernetes comes later; Docker and a working CI pipeline come first.",
        "working_on": "Migrating forty internal services to a shared Kubernetes platform with standard logging and alerts.",
        "learn_next": "Containerize your senior project, add a GitHub Actions workflow that runs your tests, then deploy it somewhere free.",
        "skills": ["docker", "kubernetes", "cicd", "monitoring"], "days_ago": 15,
    },
    {
        "author_name": "Luis Ortega", "author_role": "Application Security Engineer", "author_org": "Gulf Coast Software (fictional)", "years": 8,
        "headline": "Every developer is a security engineer now.",
        "quote": "Most of the vulnerabilities I find are a missing ownership check, not some exotic exploit.",
        "body": "When an API trusts an ID from the browser, any user can read anyone's data. Check ownership on the server, every time. It's the single most valuable security habit a student developer can build.",
        "working_on": "Adding automated security tests to our pipeline that try to read other users' records on every API route.",
        "learn_next": "Read the OWASP Top 10, then try to break your own class project: change an ID in a request and see what happens.",
        "skills": ["secure-coding", "auth", "security-fundamentals", "testing"], "days_ago": 20,
    },
]

STUDENT_A_SKILLS = [
    ("python", 4, "Built a Flask REST API for my senior project"), ("sql", 4, "CSC 312 group database project"),
    ("data-modeling", 3, "Designed the COMPASS ERD"), ("linux", 3, "Daily Ubuntu use; shell scripts for lab work"),
    ("networking", 3, "CSC 435 Computer Networks"), ("communication", 4, "Presented sprint reviews to faculty"),
    ("git", 3, "Team repository with pull requests"), ("data-structures", 4, "TA for Data Structures & Algorithms"),
    ("java", 3, "CSC 216 coursework"), ("security-fundamentals", 2, "CSC 440 coursework"),
    ("aws", 2, "Deployed an EC2 instance in class lab"), ("teamwork", 3, "Four-person senior project team"),
]
STUDENT_A_HISTORY = [  # older snapshots, for the Journey view
    (120, "Start of Fall semester", {"python": 3, "sql": 3, "data-modeling": 2, "linux": 2, "networking": 2, "communication": 3, "git": 2, "data-structures": 3, "java": 3, "teamwork": 3}),
    (45, "Midterm check-in", {"python": 3, "sql": 4, "data-modeling": 3, "linux": 2, "networking": 3, "communication": 3, "git": 3, "data-structures": 4, "java": 3, "security-fundamentals": 2, "teamwork": 3}),
]
STUDENT_B_SKILLS = [("java", 3, "Coursework"), ("sql", 2, "Coursework"), ("security-fundamentals", 3, "Security club")]

DEMO_ACCOUNTS = [
    ("student.a@compass.test", "CompassDemo-A1", "Jordan Rivera", "Computer Science", "Cloud engineering, back-end development", "active"),
    ("student.b@compass.test", "CompassDemo-B2", "Taylor Brooks", "Computer Science", "Cybersecurity", "active"),
    ("disabled@compass.test", "CompassDemo-X9", "Casey Disabled", "Computer Science", "", "disabled"),
]


class Command(BaseCommand):
    help = "Seed COMPASS with synthetic reference data and demo accounts."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete and recreate the demo accounts.")

    @transaction.atomic
    def handle(self, *args, reset=False, **opts):
        for sid, name, cat, aliases, desc, why in SKILLS:
            Skill.objects.update_or_create(
                skill_id=sid, defaults={"name": name, "category": cat, "aliases": aliases, "description": desc, "why_it_matters": why}
            )
        for cid, code, name, skills in COURSES:
            course, _ = UniversityCourse.objects.update_or_create(course_id=cid, defaults={"course_code": code, "course_name": name})
            for sid, lvl in skills:
                CourseSkill.objects.update_or_create(course=course, skill_id=sid, defaults={"coverage_level": lvl})

        for slug, title, summary, reqs in CAREERS:
            profile = CareerProfile.objects.filter(slug=slug).order_by("-version").first()
            if profile is None:
                profile = CareerProfile.objects.create(slug=slug, version=1, title=title, summary=summary)
                for sid, lvl, w, m in reqs:
                    CareerRequirement.objects.create(profile=profile, skill_id=sid, required_level=lvl, weight=w, mandatory=m)

        for p in POSTINGS:
            posting = JobPosting.objects.filter(owner__isnull=True, title=p["title"], company=p["company"]).first()
            if posting is None:
                posting = JobPosting.objects.create(
                    title=p["title"], company=p["company"], location=p["location"], tags=p["tags"], description=p["description"]
                )
                for sid, lvl, w, m in p["reqs"]:
                    PostingRequirement.objects.create(posting=posting, skill_id=sid, required_level=lvl, weight=w, mandatory=m)

        today = timezone.localdate()
        for n in FIELD_NOTES:
            note, _ = FieldNote.objects.update_or_create(
                author_name=n["author_name"],
                defaults={
                    "author_role": n["author_role"], "author_org": n["author_org"], "years_experience": n["years"],
                    "headline": n["headline"], "quote": n["quote"], "body": n["body"], "working_on": n["working_on"],
                    "learn_next": n["learn_next"], "is_sample": True, "published_at": today - timedelta(days=n["days_ago"]),
                },
            )
            note.skills.set(n["skills"])

        if reset:
            Account.objects.filter(email__in=[a[0] for a in DEMO_ACCOUNTS]).delete()

        for email, pw, name, major, interests, status in DEMO_ACCOUNTS:
            account = Account.objects.filter(email=email).first()
            if account is None:
                account = Account.objects.create_user(email=email, password=pw, status=status)
                Student.objects.create(account=account, name=name, major=major, career_interests=interests)
                self._populate(account.student, email)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Skill.objects.count()} skills, {UniversityCourse.objects.count()} courses, "
            f"{CareerProfile.objects.count()} career profiles, {JobPosting.objects.filter(owner__isnull=True).count()} sample postings, "
            f"{FieldNote.objects.count()} field notes, {len(DEMO_ACCOUNTS)} demo accounts."
        ))

    def _populate(self, student, email):
        now = timezone.now()
        if email.startswith("student.a"):
            for days, label, levels in STUDENT_A_HISTORY:
                buckets = {}
                for sid, lvl in levels.items():
                    buckets.setdefault(Skill.objects.get(pk=sid).category, []).append(lvl)
                ProgressSnapshot.objects.create(
                    student=student, label=label, skills=levels,
                    categories=skillprint.category_scores(buckets), created_at=now - timedelta(days=days),
                )
            for sid, lvl, ev in STUDENT_A_SKILLS:
                StudentSkill.objects.create(student=student, skill_id=sid, level=lvl, evidence=ev, source="self")
            for cid, term in [("csc228", "Spring 2025"), ("csc312", "Fall 2025"), ("csc435", "Fall 2026"), ("csc450", "Fall 2026")]:
                StudentCourse.objects.create(student=student, course_id=cid, term=term)
            # An earlier comparison computed honestly from the midterm skill levels,
            # so the readiness trend on the dashboard is real algorithm output.
            cloud = CareerProfile.objects.get(slug="cloud-engineer", version=1)
            mid_levels = STUDENT_A_HISTORY[1][2]
            out = comparison.compare(mid_levels, comparison.requirements_for_career(cloud))
            MatchResult.objects.create(
                student=student, target_type="career", career_profile=cloud, target_title=cloud.title,
                target_version=cloud.version, algorithm_version=out["algorithm_version"], score=out["score"],
                status=out["status"], mandatory_met=out["mandatory_met"], mandatory_total=out["mandatory_total"],
                requirements_met=out["requirements_met"], requirements_total=out["requirements_total"],
                detail=out["detail"], input_snapshot=out["snapshot"], created_at=now - timedelta(days=45),
            )
            comparison.run_and_save(student, career=cloud)
        elif email.startswith("student.b"):
            for sid, lvl, ev in STUDENT_B_SKILLS:
                StudentSkill.objects.create(student=student, skill_id=sid, level=lvl, evidence=ev, source="self")
