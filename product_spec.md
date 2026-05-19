# Product Spec v0.1 – Decision Shop
A decision-making ecommerce agent that helps users choose, not just search.



## Differentiation

### Ecom_agent vs Traditional Websites (Trendyol, Amazon, etc.)
- Websites are optimized for **search and browsing**, not decision-making  
- Users must manually compare products, read reviews, and filter noise  
- Little to no explanation of *why* one option is better than another  

✅ Ecom_agent:
- Builds a **short, structured shortlist**
- Explicitly shows **trade-offs (pros / cons)**
- Reduces decision time instead of increasing browsing time  

---

### Ecom_agent vs ChatGPT / General AI (current state)
- ChatGPT may give **generic recommendations** or inconsistent sourcing  
- Lacks reliable **product grounding and tracking of links**
- Limited **shopping workflow (constraints → shortlist → follow-up)**

✅ This agent:
- Uses **real product links from specific marketplaces (Amazon, Trendyol)**
- Keeps a **shopping session context** (constraints, follow-ups)
- Is optimized for **structured decisions, not general answers**

⚠️ If ChatGPT improves to:
- consistently retrieve real product data
- maintain shopping session memory
- provide structured comparison outputs

→ then:
- the gap becomes smaller and should be re-evaluated

---

### Core Differentiation
This is not a search tool and not a general chatbot.

It is a **decision-making ecommerce agent** that:
- combines structured search + ranking + reasoning
- explains *why* to choose something
- guides the user toward a decision, not just options


ICP.MD
## Target User (ICP)

### What ICP means
ICP (Ideal Customer Profile) defines **who your product is built for** — the users who get the most value from it and are most likely to use it.

---

### ICP for this product

**Primary user:**
People making considered purchases (e.g. shoes, electronics, home items) who feel overwhelmed by too many options and low-quality search results.

**Characteristics:**
- Searches with constraints (budget, brand, use case)
- Gets lost between multiple tabs, comparisons, and reviews
- Wants a fast, confident decision—not endless browsing
- Shops on marketplaces like Amazon / Trendyol but struggles to compare efficiently

---

### Why this matters

Defining ICP helps you:
- Focus the agent on **real user problems** (decision-making, not browsing)
- Avoid building irrelevant features
- Design better outputs (comparisons, trade-offs, follow-ups)
- Make your product clearly different from “generic search tools”

👉 Without ICP:
you build a general tool  
👉 With ICP:
you build a **useful product for a specific need**


JTBD.MD
## Job To Be Done

### What JTBD means
JTBD (Job To Be Done) defines the **core problem the user is trying to solve**, independent of the interface or tool.

It answers:
- Why does the user “hire” this product?
- What outcome are they trying to achieve?

---

### JTBD for this product

When I am trying to buy a product under specific constraints  
(e.g. budget, brand, use case),  

I don’t want to:
- browse dozens of pages
- compare manually
- guess which option is better  

I want to:
- quickly see a **small set of good options**
- understand the **trade-offs clearly**
- feel confident in my decision  

---

### What problem this solves

- Information overload (too many products, too much noise)
- Lack of structured comparison
- Decision fatigue during shopping

---

### Why this matters

JTBD helps you:
- Build for the **actual user goal (decision)** instead of surface actions (search)
- Design outputs around **clarity + confidence**, not just results
- Avoid turning the agent into “just another search tool”

👉 Without JTBD:
you optimize for features  
👉 With JTBD:
you optimize for **user outcome (better decisions faster)**


## Non-Goals

### What Non-Goals mean
Non-Goals define what the product **explicitly will NOT do**.

They are as important as features because they:
- prevent scope creep
- keep the product focused
- avoid misleading users

---

### Non-Goals for this product

This agent will NOT:
- Guarantee real-time prices or stock availability
- Scrape or verify detailed reviews beyond retrieved data
- Provide logistics-level accuracy (shipping time, local availability)
- Cover every e-commerce platform (focus is limited: Amazon + Trendyol)
- Act as a full marketplace or checkout system

---

### What problem this solves

Without non-goals:
- the product tries to do everything → becomes slow and unfocused
- users may expect accuracy you cannot guarantee
- development time explodes (infinite features)

---

### Why this matters

Non-Goals help you:
- stay focused on the **core value (decision support)**
- avoid building wrong features early
- set correct user expectations (trust)

👉 When you read this:
you should understand **what this product is NOT trying to be**

👉 This is how you keep a project:
simple, fast, and differentiated

success_metrics.MD
## Success Metrics

### What Success Metrics mean
Success Metrics define **how you measure whether your product is actually working**.

They answer:
- Is the product useful?
- Are users getting value?
- Is the core problem being solved?

---

### Success Metrics for this product

- Number of shopping sessions (e.g. queries made by users)
- Click-through rate (did users click suggested products?)
- Follow-up rate (do users continue the conversation?)
- Number of sessions that lead to at least one product click
- Qualitative feedback (did users find results useful?)

---

### What problem this solves

Without metrics:
- you don’t know if your agent is helpful
- you can’t improve ranking or explanations
- you may build features users don’t need

---

### Why this matters

Success Metrics help you:
- validate if your agent improves decision-making
- focus on **real user behavior (clicks, actions)**, not assumptions
- iterate quickly based on data

👉 When you read this:
you should understand **what “good” looks like for your product**

👉 This is how you move from:
“it works”
→ to
“it actually helps users”


user_journeys.MD
## User Journeys

### What User Journeys mean
User Journeys describe **how a user interacts with your product step by step**.

They help you visualize:
- what the user does
- what the system responds
- how the experience flows from start to decision

---

### User Journeys for this product

#### Journey 1 — Constrained search
User: “running shoes under $100”

1. User enters query  
2. Agent extracts constraints (budget, category)  
3. Agent searches and ranks products  
4. Agent returns 3–5 options with trade-offs  
5. User clicks a product  

---

#### Journey 2 — Clarification needed
User: “best headphones”

1. User enters vague query  
2. Agent asks follow-up: “What is your budget?”  
3. User responds  
4. Agent generates shortlist + explanations  

---

#### Journey 3 — Iteration / refinement
User: “cheaper options”

1. User continues conversation  
2. Agent re-ranks with new constraint  
3. Agent updates results and explains differences  

---

### What problem this solves

Without journeys:
- you build features without understanding real usage
- UX becomes fragmented and inconsistent

---

### Why this matters

User Journeys help you:
- design the **flow, not just the output**
- identify missing steps (e.g. follow-ups, re-ranking)
- ensure the agent feels like a **guided experience**, not a static result

👉 When you read this:
you should understand **how a user moves from query → decision**

👉 This is how you turn your agent into a:
structured, interactive product — not just an API