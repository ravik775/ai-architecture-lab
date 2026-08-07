# How to Incorporate Expense AI Portfolio Project Into Your Resume
## A Guide for Job Seekers Between Roles

---

## CONTEXT: Your Situation

You left Decision Engines in **Mar 2026** and are not currently employed. You have built **Expense AI**, a production-grade agentic AI platform, as a portfolio project to:

1. ✅ Demonstrate current AI architecture expertise
2. ✅ Show you're staying current with modern tools (LangGraph, LiteLLM, etc.)
3. ✅ Provide a tangible example of what you can do
4. ✅ Explain what you've been doing since leaving your last job

This is a **strength**, not a weakness—if positioned correctly.

---

## SECTION 1: HOW TO PRESENT IT ON YOUR RESUME

### Option A: Add to "Professional Experience" (Conservative)

**Best for:** Traditional companies, formal hiring processes

**Placement:** After Decision Engines role or as a separate role

```
PROFESSIONAL EXPERIENCE
═════════════════════════════════════════════════════════════════

Decision Engines | Senior Software Engineer (Solution Architect) - Nov 2020 – Mar 2026
[Keep existing bullets]

────────────────────────────────────────────────────────────────

Expense AI (Portfolio) | Architect & Developer - Apr 2026 – Present
Hyderabad, India

• Architected a layered, provider-independent expense-approval platform 
  using FastAPI and Pydantic v2, demonstrating current expertise in 
  production agentic AI systems, LLM provider abstraction, and resilience 
  patterns.

• Implemented LangGraph-based human-in-the-loop approval workflow with 
  PostgreSQL checkpointing, enabling workflow resumption across process 
  restarts and demonstrating durable state management for agentic systems.

• Built ChromaDB-backed RAG pipeline with deterministic corpus seeding, 
  showcasing end-to-end retrieval-augmented generation implementation without 
  external dependencies.

• Composed resilience pipeline with retry (Tenacity), timeout, cache 
  (cachetools), circuit breaker (PyBreaker), and guardrails policies; 
  integrated token/cost tracking and cost-based decision logic.

• Instrumented with OpenTelemetry tracing, structured logging, request 
  correlation, and LangSmith integration; implemented token tracking, cost 
  estimation, and sensitive data redaction for production observability.

• Packaged for multi-environment deployment using Docker Compose with health 
  checks, configuration management via Pydantic settings, and support for both 
  lightweight basic mode and full agentic mode.

Technology: FastAPI, Pydantic v2, LiteLLM, LangChain, LangGraph, ChromaDB, 
PostgreSQL, OpenTelemetry, Tenacity, PyBreaker, Docker, Python 3.12
```

**Why this works:**
- Clear about timeline (Apr 2026 – Present)
- Explicitly says "Portfolio" to indicate personal project
- Shows intentional skill development
- Demonstrates you're current with latest AI tools

---

### Option B: Create a "Featured Projects" Section (Modern)

**Best for:** Tech-forward companies, startups, director-level roles

**Placement:** After Professional Experience or in Skills section

```
FEATURED PROJECTS
═════════════════════════════════════════════════════════════════

Expense AI: Agentic AI Approval Platform
GitHub: github.com/ravik775/ai-architecture-lab

An enterprise-grade expense-analysis and approval platform demonstrating 
production-ready agentic AI architecture. Built to showcase current expertise 
in LLM provider abstraction, agentic workflows, RAG, and production safeguards.

• Architected layered design with provider-independent LLM access via LiteLLM, 
  enabling runtime switching between Claude, OpenRouter, OpenAI without code 
  changes.

• Orchestrated resumable LangGraph state machine routing low-risk to automatic 
  approval, high-value to human review; PostgreSQL checkpointing enables 
  approvals to persist across restarts.

• Implemented ChromaDB RAG pipeline with deterministic corpus seeding and 
  custom LocalHashEmbeddingFunction for reproducible, cost-free embeddings.

• Composed resilience pipeline: retry (Tenacity), timeout, cache (cachetools), 
  circuit breaker (PyBreaker), guardrails; integrated token/cost tracking and 
  cost-based routing.

• End-to-end observability: OpenTelemetry tracing, structured logging with 
  request-ID correlation, LangSmith integration, token/cost tracking, data 
  redaction.

• Deployed via Docker Compose with multi-environment support (basic mode 
  without database, agentic mode with PostgreSQL).

Stack: FastAPI, Pydantic v2, LiteLLM, LangChain, LangGraph, ChromaDB, 
PostgreSQL, OpenTelemetry, Docker, Python 3.12
```

**Why this works:**
- Separates portfolio from employment history
- Emphasizes it's intentional learning/demonstration
- Easier to update and change without modifying employment record
- Tech-forward positioning

---

### Option C: Integrate Into Decision Engines (Seamless)

**Best for:** Emphasizing career continuity

**Placement:** As subsection within Decision Engines role

```
Decision Engines | Senior Software Engineer (Solution Architect) - Nov 2020 – Mar 2026
[Keep existing bullets]

**Ongoing: Agentic AI Architecture (Portfolio Project)**

Designed and implemented production-grade agentic AI platform to maintain 
current expertise in LLM integration, agentic workflows, and modern AI 
architecture patterns.

• Architected provider-independent expense-approval platform using FastAPI, 
  Pydantic v2, LiteLLM, enabling runtime LLM provider switching without code 
  changes.

• Orchestrated LangGraph human-in-the-loop approval workflow with PostgreSQL 
  durability; implemented ChromaDB RAG, resilience patterns (retry, timeout, 
  circuit breaker, guardrails), and OpenTelemetry observability.

Technology: FastAPI, Pydantic v2, LiteLLM, LangChain, LangGraph, ChromaDB, 
PostgreSQL, OpenTelemetry, Tenacity, PyBreaker, Docker, Python 3.12
```

**Why this works:**
- Shows continuous learning (no "gap" narrative)
- Keeps work history linear
- Emphasizes you didn't stop being an architect just because you left the role

---

## SECTION 2: HOW TO TALK ABOUT IT IN INTERVIEWS

### The Interview Narrative (30–60 seconds)

**Phone Screen / Initial Call:**

"After leaving Decision Engines in March, I built an agentic AI platform to stay current with modern AI architecture. The project—Expense AI—demonstrates provider-independent LLM integration using LiteLLM, agentic workflow orchestration with LangGraph, and production resilience patterns. I specifically built it to explore how to abstract LLM vendors, design for human-in-the-loop approval with durable state using PostgreSQL, implement observability at scale with OpenTelemetry, and manage LLM costs through structured output validation and token tracking.

The project has taught me a lot about production-grade AI systems: what matters is not just calling an LLM, but designing layers that isolate business logic from vendors, building resilience into every call, making systems observable end-to-end, and thinking about cost as a first-class constraint. It's all open source on GitHub, fully tested, and ready to run locally via Docker Compose."

**Why this works:**
- Clear motivation (staying current)
- Specific technologies (LiteLLM, LangGraph, etc.)
- Shows architectural thinking (abstraction, resilience, observability)
- Demonstrates self-directed learning
- Offers to show code

---

### The "Why Portfolio Project?" Question (If Asked)

**Interview Question:** "I see you have a portfolio project. Can you explain?"

**Strong Answer:**

"Absolutely. I left Decision Engines in March 2026 and decided to build something that reflects what I believe modern agentic AI systems should look like. Rather than just job hunting, I wanted to demonstrate current expertise in three areas:

1. **Provider Abstraction:** I built a provider-independent interface using LiteLLM that lets you swap between Claude, OpenRouter, and OpenAI at runtime through configuration. This is important because no company should be locked into one vendor.

2. **Agentic Design:** I implemented a LangGraph state machine that routes low-risk items to automatic approval and high-value items to human review, with PostgreSQL checkpointing so approvals survive process restarts. This shows I understand how to design workflows that keep humans in control, not AI in control.

3. **Production Patterns:** I built a composition of resilience policies—retry, timeout, circuit breaker, caching, guardrails—showing I think about how systems fail and how to build them to recover gracefully.

I could have just updated my LinkedIn with old projects, but I wanted to show I'm still building, still learning, and staying current with tools like LangGraph and structured Pydantic outputs. It's a conversation starter and a proof point."

**Why this works:**
- Acknowledges the gap without apologizing
- Shows intentionality (not just killing time)
- Demonstrates thought leadership
- Positions portfolio as strength

---

## SECTION 3: ADDRESSING THE EMPLOYMENT GAP

### If a Recruiter Asks: "What are you doing now?"

**Recommended Answer:**

"I left Decision Engines in March after 5+ years. I'm actively job searching for an architect role—Solution Architect, AI Solution Architect, or Technical Architect—ideally with teams building agentic AI systems. While looking, I've built Expense AI, an agentic approval platform, to stay current with modern AI tools and showcase expertise in LLM provider abstraction, agentic workflows, and production observability. I'm interviewing with [companies] and expect to have something in place soon."

**Why this works:**
- Clear and confident
- Shows you're actively looking (not just taking a break)
- Positions portfolio as professional development, not unemployment
- Forward-looking

---

### If They Ask: "Why did you leave Decision Engines?"

**Recommended Answer** (adapt to your situation):

Option 1 (Role-focused):
"The role evolved toward operational support, and I wanted to return to hands-on architecture and design. I'm looking for a position where I can drive AI architecture decisions and build systems end-to-end."

Option 2 (Growth-focused):
"I wanted to focus on staying current with emerging AI patterns—agentic workflows, LLM provider management, cost optimization. Building Expense AI let me dive deep into these areas, and I'm ready to apply those insights in a production environment."

Option 3 (Strategic):
"After 5+ years in platform delivery, I wanted to explore what's happening at the frontier of AI architecture. I built a portfolio project to understand modern agentic systems better, and now I'm ready to join a team solving these problems at scale."

**Why these work:**
- Honest without being negative
- Shows intentionality
- Forward-focused (not dwelling on past)
- Connects to what you want next

---

## SECTION 4: BEST PRACTICES FOR PORTFOLIO PROJECTS ON RESUME

### ✅ DO:

1. **Be explicit about timeline:**
   - ✅ "Expense AI (Portfolio) | Apr 2026 – Present"
   - ❌ Don't hide it; be clear it's a personal project

2. **Connect it to hiring needs:**
   - ✅ If job posting mentions "agentic AI" or "LLM integration," reference the project
   - ✅ Tailor bullets to emphasize what the job cares about

3. **Make it easy to explore:**
   - ✅ Include GitHub link: "GitHub: github.com/ravik775/expense-ai"
   - ✅ Include README with setup instructions
   - ✅ Add a "See it in action" screenshot or demo video

4. **Show it's production-ready:**
   - ✅ "Docker Compose deployment," "automated testing," "health checks"
   - ✅ Mention observability and monitoring
   - ✅ Reference cost tracking and resilience patterns

5. **Update it while job hunting:**
   - ✅ Add features if interviewing with companies focused on specific areas
   - ✅ Add blog posts explaining architecture decisions
   - ✅ Record a short demo video

---

### ❌ DON'T:

1. **Don't hide that it's a portfolio project:**
   - ❌ Don't make it look like a real job without context
   - ❌ Don't omit dates or pretend it was professional work

2. **Don't oversell scope:**
   - ❌ Don't claim "millions of users" or "production impact" 
   - ✅ Do say "reference implementation" or "portfolio demonstration"

3. **Don't leave it unmaintained:**
   - ❌ Don't upload it to GitHub and forget about it
   - ✅ Keep README updated, respond to any potential collaborators

4. **Don't minimize its value:**
   - ❌ Don't say "just a side project"
   - ✅ Do say "portfolio project demonstrating current expertise"

5. **Don't duplicate it in multiple sections:**
   - ❌ Don't put it in both "Professional Experience" AND "Featured Projects"
   - ✅ Choose one placement and commit to it

---

## SECTION 5: DIFFERENT RESUME FORMATS & PLACEMENT GUIDE

### Format 1: Chronological Resume (Traditional)

**Use if:** You have a solid 19-year work history and want to show progression

```
Professional Experience
├── Decision Engines (2020-2026) ← Keep
├── Senos Tech (2018-2020) ← Keep
├── BA Continuum (2015-2018) ← Keep
├── [Other roles...]
│
└── Expense AI (Portfolio) - Apr 2026 – Present ← Add as last entry
    (Shows you're continuing to grow)
```

**Pros:**
- Clear timeline
- Shows continuous career progression
- Portfolio is clearly supplementary

**Cons:**
- Current role is a portfolio project (not ideal for traditional companies)

---

### Format 2: Hybrid Resume (Best for You)

**Use if:** You want to emphasize both stability and current expertise

```
Professional Experience
├── Decision Engines (2020-2026) ← Keep
├── [Previous roles...]

Featured Projects & Ongoing Learning
├── Expense AI: Agentic AI Platform ← Add here
   (GitHub: github.com/ravik775/expense-ai)
```

**Pros:**
- Clear separation between employment and learning
- Doesn't make portfolio look like a job
- Shows intentional skill development
- Modern and sophisticated

**Cons:**
- Requires discipline to keep "Featured Projects" current
- Some ATS systems may not parse it well

---

### Format 3: Skills-First Resume (Modern/Tech-Forward)

**Use if:** You're applying to startups or director-level roles

```
Technical Leadership & AI Architecture
- 19+ years architecting enterprise platforms
- Specialized in agentic AI, LLM integration, production resilience
- Recent focus: provider-independent LLM abstraction, human-in-the-loop workflows

Core Expertise
- AI Architecture, LLM Integration, RAG, Agentic Workflows
- [Skills table...]

Featured Work & Projects
├── Expense AI (Portfolio) - Apr 2026 – Present
├── Decision Engines (2020-2026)
├── [Other key projects...]
```

**Pros:**
- Emphasizes expertise over chronology
- Portfolio feels natural and current
- Modern companies love this format

**Cons:**
- Some traditional companies want strict chronological format
- Requires careful tailoring per role

---

## SECTION 6: HOW TO SET UP GITHUB FOR MAXIMUM IMPACT

### Repository Setup

**Step 1: Create clear README**
```markdown
# Expense AI: Agentic Expense Approval Platform

A production-oriented reference architecture for agentic AI systems.

## Quick Start
- Docker Compose setup in 5 minutes
- No external dependencies for local demo
- Full observability: OpenTelemetry, structured logging, LangSmith

## Key Features
- Provider-independent LLM access (LiteLLM)
- Human-in-the-loop approval workflow (LangGraph)
- RAG with ChromaDB
- Resilience pipeline (retry, timeout, circuit breaker, guardrails)
- Observability (OpenTelemetry, structured logging, cost tracking)

## Architecture
[Include architecture diagram from README.md]

## Technologies
FastAPI, Pydantic v2, LiteLLM, LangGraph, ChromaDB, PostgreSQL, 
OpenTelemetry, Docker
```

**Step 2: Make it easy to run**
```bash
# User should be able to:
git clone https://github.com/ravik775/expense-ai.git
cd expense-ai
docker compose up
curl http://localhost:8000/docs
```

**Step 3: Add examples**
- Example API calls in README
- Screenshot of health check
- Short demo video (5 minutes)

**Step 4: Pin the repo on GitHub**
- Make it your first visible project
- Recruiters see it immediately

---

## SECTION 7: TALKING POINTS FOR DIFFERENT INTERVIEW SCENARIOS

### Scenario 1: "Why should we hire you for this AI Architecture role?"

**Your Answer:**

"I've spent the last [X weeks] building Expense AI, an agentic AI platform that solves exactly the problems we're discussing. I designed it to explore:

1. **How to abstract LLM vendors** – I used LiteLLM to enable runtime provider switching. This matters because if you commit to one vendor, you're stuck if pricing changes or a better model launches.

2. **How to keep humans in the loop** – I built a LangGraph state machine that routes high-risk items to human review with PostgreSQL checkpointing, so approvals survive restarts. This is critical for any business-sensitive workflow.

3. **How to build resilience without making code unreadable** – Instead of scattered error handling, I composed a policy pipeline: retry, timeout, circuit breaker, cache, guardrails. Each is testable and reusable.

4. **How to observe AI systems end-to-end** – I instrumented with OpenTelemetry, structured logging, token tracking, cost estimation, and LangSmith. If something goes wrong, you know where and why.

The system is production-ready, fully tested, and deployed via Docker Compose. It's a conversation starter about how I approach AI architecture: layered design, vendor neutrality, human oversight, resilience, and observability first."

---

### Scenario 2: "This is a senior role. Tell us about your last major project."

**Your Answer:**

"My last role at Decision Engines was leading a 6-engineer team on an event-driven invoice processing platform—that project I can speak to with specifics. But more recently, I've been focused on building expertise in agentic AI systems.

I built Expense AI as a deliberate learning project. Rather than passively reading about LangGraph, LiteLLM, and production AI patterns, I implemented a working system that demonstrates how each piece fits together: provider abstraction, agentic workflows with human approval, RAG, resilience pipelines, and observability. The project forced me to make real architectural decisions—which I think is important at this stage of my career.

If you were hiring me, this is the kind of thinking you'd get: deliberate, pragmatic, and grounded in production realities. I'm not just reading about best practices; I'm building and testing them."

---

### Scenario 3: "Tell us about your experience with [specific tool: LangGraph, LiteLLM, etc.]"

**Your Answer:**

"I've built production systems with [tool]. In Expense AI, I used LangGraph to model an approval workflow as a state machine: low-risk items auto-approve, high-value items interrupt and wait for human review, then resume. The key insight is that LangGraph's checkpoint model lets you persist state to PostgreSQL, so an approval can survive a process restart—critical for durability.

I specifically chose LangGraph over simpler approaches because [explain reasoning]. The tradeoff was [acknowledged complexity], but it gave us [benefits]. Here's what I learned: [insight from the project].

If your system needs [requirement], LangGraph is strong because [specific capability]. If you need [other requirement], there are simpler options. I can walk you through the decision tree."

---

## SECTION 8: 30-SECOND ELEVATOR PITCH (For Networking)

**At a conference or networking event, when someone asks "What do you do?":**

"I'm an AI architect with 19+ years building enterprise systems. I recently left a role at Decision Engines leading invoice-processing platforms, and I've spent the last few months building Expense AI—an agentic AI platform for approval workflows. It's a showcase project demonstrating how to architect resilient, observable AI systems with provider-independent LLM access and human-in-the-loop workflows.

I'm actively looking for an architect role—either Solution Architect or Technical Architect focused on agentic AI or LLM platforms. If you know of anything interesting or want to see the project, I'm happy to chat."

**Why this works:**
- Clear introduction
- Explains your status (not employed, but actively seeking)
- Portfolio project positioned as intentional, not desperate
- Call to action (networking)

---

## SECTION 9: WHAT TO DO NEXT (Action Plan)

### Immediate (This Week)
- [ ] Finalize resume with portfolio section (use Option B: "Featured Projects")
- [ ] Update GitHub README with demo video and quick-start guide
- [ ] Write 3 versions of your "gap" explanation (pick the one that feels most true)

### Short-term (Weeks 2–4)
- [ ] Create LinkedIn post about Expense AI (1–2 paragraphs, link to GitHub)
- [ ] Record 5-minute demo video (running the app, showing key features)
- [ ] Add blog post to GitHub repository explaining 1–2 architecture decisions
- [ ] Update your LinkedIn headline to emphasize AI architecture

### Medium-term (Weeks 4–12)
- [ ] Job applications: Mention Expense AI in cover letters for AI/agentic roles
- [ ] Networking: Share the project with contacts, ask for introductions
- [ ] If no offers yet: Consider adding a feature (e.g., multi-tenant support) or writing more documentation

---

## SECTION 10: COMMON CONCERNS & HOW TO ADDRESS THEM

### Concern 1: "Won't the resume look like I'm not working?"

**Reality:** No, if you frame it clearly. A portfolio project shows you're:
- Still learning
- Staying current with AI
- Intentional about career development
- Not stagnating

**How to present it:**
✅ "Expense AI (Portfolio) | Apr 2026 – Present"
✅ Include it under "Featured Projects" section
✅ In interviews, explain it as intentional (staying current)

---

### Concern 2: "Is it OK to claim expertise based on a side project?"

**Reality:** Yes, if the project is substantial and production-ready.

Your Expense AI project is:
✅ ~3000+ lines of production code
✅ Fully tested (pytest)
✅ Deployed (Docker Compose)
✅ Observable (OpenTelemetry, structured logging)
✅ Documented (comprehensive README)

This is not a toy project. It's a legitimate portfolio piece.

---

### Concern 3: "Shouldn't I list my employment gap differently?"

**Reality:** Transparency is best. Options:

Option A (Direct):
```
Decision Engines | Senior Software Engineer (Solution Architect) - Nov 2020 – Mar 2026

Expense AI | Architect (Portfolio Project) - Apr 2026 – Present
```

Option B (Resume-focused, cover letter explains gap):
```
Professional Experience
- Decision Engines (2020-2026)
- [Previous roles]

Featured Projects
- Expense AI: Agentic AI Platform (2026)
```
*In cover letter:* "After leaving Decision Engines in March, I built Expense AI to stay current with agentic AI architecture..."

Option C (Most conservative):
```
Professional Experience
- Decision Engines (2020-2026)

Recent Focus: AI Architecture & Agentic Systems
Built production-grade platform demonstrating LLM provider abstraction, 
agentic workflows, RAG, and resilience patterns. Available to view on GitHub.
```

**Choose the one that matches your industry norms** (tech startups → Option A/B; traditional enterprise → Option B/C).

---

### Concern 4: "What if someone looks at the code and doesn't like it?"

**Reality:** Code can always be better, but:

✅ Your code is clean, layered, and well-organized
✅ It follows best practices (dependency injection, composition, separation of concerns)
✅ It's tested
✅ It's documented

**If someone has feedback:** "I'm always open to improving. What would you change?" (This shows you're not defensive and still learning.)

---

## SECTION 11: FINAL CHECKLIST

Before you start applying, make sure you have:

### Resume:
- [ ] Portfolio project section added (pick your format)
- [ ] AI expertise emphasized in Executive Profile
- [ ] Core Expertise table expanded (5 AI rows)
- [ ] Decision Engines bullets kept intact
- [ ] GitHub link included in portfolio section

### GitHub:
- [ ] README is complete and clear
- [ ] Quick-start works (docker compose up)
- [ ] Demo video or screenshots included
- [ ] Tests pass
- [ ] Repository is pinned on your profile

### Interview Prep:
- [ ] 30-second pitch written and practiced
- [ ] Answer to "Why portfolio project?" prepared
- [ ] Answer to "Why did you leave?" prepared
- [ ] 3 talking points about Expense AI ready

### Networking:
- [ ] LinkedIn headline updated to mention AI architecture
- [ ] LinkedIn summary mentions Expense AI
- [ ] GitHub link on LinkedIn profile
- [ ] Ready to send GitHub link when asked "What have you built?"

---

## SUMMARY: POSITIONING YOUR PORTFOLIO PROJECT

Your Expense AI project is a **strength**, not a weakness. Here's why:

1. **Shows continuous learning** – You didn't stop being an architect when you left
2. **Demonstrates current skills** – LangGraph, LiteLLM, agentic workflows are hot topics
3. **Provides proof** – Instead of claiming AI expertise, you can show it
4. **Tells a story** – "I built this to stay current and explore agentic AI patterns"
5. **Gives interviewers something to discuss** – "Walk me through your architecture decisions"

**The key is confidence.** Own it. This is not a resume gap; it's professional development. Hiring managers at forward-thinking companies will respect it.

---

## RESOURCES

- **All-in-one GitHub link:** github.com/ravik775/ai-architecture-lab/expense-ai
- **Interview talking points file:** (in outputs folder)
- **Resume templates:** (in outputs folder)
- **LinkedIn description examples:** (in outputs folder)

Good luck with your job search. The project speaks for itself.
