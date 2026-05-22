from __future__ import annotations

import os
import time
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template_string, request, session

from .agent import ShoppingSearchAgent
from .config import Settings
from .decision_summary import (
    build_decision_summary,
    build_follow_up_chips,
    build_shareable_markdown,
)
from .event_tracking import record_event, reset_session_preferences
from .limits import MAX_QUERY_LENGTH, MAX_SESSIONS
from .query_metrics import classify_outcome, record_chat_request
from .serpapi_client import SerpApiSearchError


HTML_PAGE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Shopping Search Agent Chat</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 0; background: #f6f8fb; color: #1f2937; }
      .wrap { max-width: 900px; margin: 0 auto; padding: 24px 16px; }
      h1 { font-size: 24px; margin: 0 0 8px; }
      p.note { margin: 0 0 16px; color: #4b5563; }
      .chat { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 16px; min-height: 340px; }
      .msg { margin-bottom: 14px; }
      .user { font-weight: bold; color: #0f766e; }
      .bot { font-weight: bold; color: #1d4ed8; }
      .bubble { white-space: pre-wrap; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; line-height: 1.45; }
      .bubble-intro { margin-bottom: 10px; }
      .product-list { list-style: none; margin: 0; padding: 0; }
      .product-list li { margin-bottom: 10px; }
      .product-list a { color: #2563eb; text-decoration: none; font-weight: 600; }
      .product-list a:hover { text-decoration: underline; }
      .product-meta { color: #64748b; font-size: 13px; margin-top: 2px; }
      form { display: flex; gap: 10px; margin-top: 14px; }
      input { flex: 1; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; }
      button { padding: 10px 14px; border: 0; border-radius: 8px; background: #2563eb; color: #fff; cursor: pointer; }
      button:disabled { background: #94a3b8; cursor: not-allowed; }
      .controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 12px 0 0; font-size: 13px; }
      .controls label { display: flex; align-items: center; gap: 6px; cursor: pointer; }
      .controls button.secondary { background: #e2e8f0; color: #334155; }
      .why-panel { display: none; margin-top: 6px; padding: 8px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; font-size: 12px; color: #1e3a8a; line-height: 1.4; }
      .why-panel.visible { display: block; }
      .decision-summary { margin-top: 12px; padding: 10px 12px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; font-size: 13px; line-height: 1.5; color: #14532d; }
      .decision-summary strong { display: block; margin-bottom: 6px; color: #166534; }
      .follow-up-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
      .follow-up-chips button.chip { padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 999px; background: #fff; color: #334155; font-size: 13px; cursor: pointer; }
      .follow-up-chips button.chip:hover { background: #f1f5f9; border-color: #94a3b8; }
      .artifact-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
      .artifact-actions button.secondary { background: #e2e8f0; color: #334155; font-size: 13px; }
      .artifact-actions .copy-status { font-size: 12px; color: #15803d; align-self: center; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1>Shopping Search Agent Chat</h1>
      <p class="note">Ask shopping requests and get a conversational answer with recommendations.</p>
      <div id="chat" class="chat"></div>
      <div class="controls">
        <label><input type="checkbox" id="showWhy" /> Why you&rsquo;re seeing this</label>
        <label><input type="checkbox" id="personalizationOn" checked /> Use click personalization</label>
        <button type="button" id="resetPrefs" class="secondary">Reset my clicks</button>
      </div>
      <form id="form">
        <input id="query" maxlength="500" placeholder="I need waterproof running shoes for women under $120" />
        <button id="send" type="submit">Send</button>
      </form>
    </div>
    <script>
      const SESSION_ID = {{ session_id|tojson }};
      const chat = document.getElementById("chat");
      const form = document.getElementById("form");
      const query = document.getElementById("query");
      const send = document.getElementById("send");
      const showWhy = document.getElementById("showWhy");
      const personalizationOn = document.getElementById("personalizationOn");
      const resetPrefs = document.getElementById("resetPrefs");
      const MAX_SHOWN_PRODUCTS = 5;

      function trackEvent(payload) {
        fetch("/api/track_event", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ ...payload, session_id: SESSION_ID }),
        }).catch(() => {});
      }

      function trackImpressions(shortlist) {
        shortlist.forEach((item, index) => {
          trackEvent({
            event_type: "impression",
            url: item.url || "",
            domain: item.domain || "",
            position: index + 1,
          });
        });
      }

      function onProductClick(event, item, position) {
        event.preventDefault();
        trackEvent({
          event_type: "product_click",
          url: item.url || "",
          domain: item.domain || "",
          position,
        });
        if (item.url) {
          window.open(item.url, "_blank", "noopener,noreferrer");
        }
      }

      function appendMessage(role, text) {
        const div = document.createElement("div");
        div.className = "msg";
        const who = role === "user" ? "user" : "bot";
        const title = document.createElement("div");
        title.className = who;
        title.textContent = role === "user" ? "You" : "Agent";
        const bubble = document.createElement("div");
        bubble.className = "bubble";
        bubble.textContent = text;
        div.appendChild(title);
        div.appendChild(bubble);
        chat.appendChild(div);
        chat.scrollTop = chat.scrollHeight;
      }

      function appendBotResponse(data) {
        const div = document.createElement("div");
        div.className = "msg";
        const title = document.createElement("div");
        title.className = "bot";
        title.textContent = "Agent";
        const bubble = document.createElement("div");
        bubble.className = "bubble";

        const intro = document.createElement("div");
        intro.className = "bubble-intro";
        intro.textContent = data.ui_intro || data.message || "No response.";
        bubble.appendChild(intro);

        const shortlist = (data.shortlist || []).slice(0, MAX_SHOWN_PRODUCTS);
        if (shortlist.length) {
          const list = document.createElement("ul");
          list.className = "product-list";
          shortlist.forEach((item, index) => {
            const position = index + 1;
            const li = document.createElement("li");
            const link = document.createElement("a");
            link.href = item.url || "#";
            link.textContent = `${position}) ${item.title || "Untitled result"}`;
            link.addEventListener("click", (e) => onProductClick(e, item, position));
            li.appendChild(link);

            const meta = document.createElement("div");
            meta.className = "product-meta";
            const bits = [item.domain, item.explanation].filter(Boolean);
            meta.textContent = bits.join(" — ");
            if (meta.textContent) li.appendChild(meta);

            if (item.why_seeing_this) {
              const why = document.createElement("div");
              why.className = "why-panel";
              why.dataset.whyText = item.why_seeing_this;
              why.textContent = "Why you\u2019re seeing this: " + item.why_seeing_this;
              if (showWhy.checked) why.classList.add("visible");
              li.appendChild(why);
            }

            list.appendChild(li);
          });
          bubble.appendChild(list);
          trackImpressions(shortlist);

          const summaryLines = data.decision_summary || [];
          if (summaryLines.length) {
            const summary = document.createElement("div");
            summary.className = "decision-summary";
            const heading = document.createElement("strong");
            heading.textContent = "Decision summary";
            summary.appendChild(heading);
            summaryLines.forEach((line) => {
              const row = document.createElement("div");
              row.textContent = line;
              summary.appendChild(row);
            });
            bubble.appendChild(summary);
          }

          const artifactMarkdown = data.decision_artifact_markdown || "";
          if (artifactMarkdown) {
            const actions = document.createElement("div");
            actions.className = "artifact-actions";
            const copyBtn = document.createElement("button");
            copyBtn.type = "button";
            copyBtn.className = "secondary";
            copyBtn.textContent = "Copy decision memo";
            const status = document.createElement("span");
            status.className = "copy-status";
            status.setAttribute("aria-live", "polite");
            copyBtn.addEventListener("click", async () => {
              try {
                await navigator.clipboard.writeText(artifactMarkdown);
                status.textContent = "Copied.";
              } catch (err) {
                status.textContent = "Copy failed.";
              }
            });
            actions.appendChild(copyBtn);
            actions.appendChild(status);
            bubble.appendChild(actions);
          }

          const chips = data.follow_up_chips || [];
          if (chips.length) {
            const chipRow = document.createElement("div");
            chipRow.className = "follow-up-chips";
            chips.forEach((chip) => {
              const btn = document.createElement("button");
              btn.type = "button";
              btn.className = "chip";
              btn.textContent = chip.label || "Refine";
              btn.addEventListener("click", () => runFollowUpQuery(chip.query || chip.label || ""));
              chipRow.appendChild(btn);
            });
            bubble.appendChild(chipRow);
          }
        }

        div.appendChild(title);
        div.appendChild(bubble);
        chat.appendChild(div);
        chat.scrollTop = chat.scrollHeight;
      }

      function refreshWhyPanels() {
        document.querySelectorAll(".why-panel").forEach((panel) => {
          panel.classList.toggle("visible", showWhy.checked);
        });
      }

      showWhy.addEventListener("change", refreshWhyPanels);

      async function postPreferences(body) {
        const res = await fetch("/api/preferences", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body),
        });
        return res.json();
      }

      personalizationOn.addEventListener("change", async () => {
        await postPreferences({ enabled: personalizationOn.checked });
      });

      resetPrefs.addEventListener("click", async () => {
        await postPreferences({ reset: true });
        appendMessage("bot", "Cleared your click history for this session. Future results will not use past clicks until you click products again.");
      });

      async function runFollowUpQuery(text) {
        const trimmed = String(text || "").trim();
        if (!trimmed) return;
        trackEvent({ event_type: "message_send", message_text: trimmed });
        appendMessage("user", trimmed);
        send.disabled = true;
        try {
          const res = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({ query: trimmed }),
          });
          const data = await res.json();
          if (!res.ok) {
            const msg = data.search_failed
              ? (data.error || data.detail || "Search failed.")
              : (data.error || "Request failed.");
            appendMessage("bot", msg);
          } else {
            appendBotResponse(data);
          }
        } catch (err) {
          appendMessage("bot", `Error: ${String(err)}`);
        } finally {
          send.disabled = false;
          query.focus();
        }
      }

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = query.value.trim();
        if (!text) return;
        query.value = "";
        await runFollowUpQuery(text);
      });
    </script>
  </body>
</html>
"""


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "shopping-search-agent-dev-secret")
settings = Settings()
agent = ShoppingSearchAgent(settings)
_CHAT_STATE: dict[str, dict[str, Any]] = {}

_CHAT_RATE_LIMIT = 5
_CHAT_RATE_WINDOW_SECONDS = 10.0
_CHAT_RATE_BUCKETS: dict[str, list[float]] = {}


def _get_session_id() -> str:
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid4())
        session["session_id"] = session_id
    return str(session_id)


def _personalization_enabled() -> bool:
    return bool(session.get("personalization_enabled", True))


def _chat_rate_limit_key(session_id: str) -> str:
    return f"session:{session_id}"


def _ensure_chat_session_allowed(session_id: str) -> str | None:
    if session_id in _CHAT_STATE:
        return None
    if len(_CHAT_STATE) >= MAX_SESSIONS:
        return "Too many active sessions"
    return None


def _check_chat_rate_limit(session_id: str) -> str | None:
    """Return an error message when the limit is exceeded, else None."""
    key = _chat_rate_limit_key(session_id)
    now = time.monotonic()
    cutoff = now - _CHAT_RATE_WINDOW_SECONDS
    recent = [t for t in _CHAT_RATE_BUCKETS.get(key, []) if t > cutoff]
    if len(recent) >= _CHAT_RATE_LIMIT:
        _CHAT_RATE_BUCKETS[key] = recent
        return "Too many requests, please slow down"
    recent.append(now)
    _CHAT_RATE_BUCKETS[key] = recent
    return None


def _looks_like_follow_up(user_query: str) -> bool:
    lowered = user_query.lower()
    follow_up_terms = (
        "which one",
        "which",
        "difference",
        "recommend",
        "better",
        "best one",
        "compare",
        "among these",
        "from these",
        "these options",
        "those options",
        "what about",
        "can you refine",
        "filter",
        "cheaper",
        "durable",
        "durability",
        "retailer",
        "retailers",
        "top two",
        "top 2",
    )
    return any(term in lowered for term in follow_up_terms)


def _is_compare_or_recommend_query(user_query: str) -> bool:
    lowered = user_query.lower()
    terms = ("which", "recommend", "difference", "better", "best", "compare")
    return any(term in lowered for term in terms)


def _build_contextual_query(user_query: str, previous_response: dict) -> str:
    constraints = previous_response.get("constraints", {}) or {}
    product_type = str(constraints.get("product_type") or "").strip()
    attributes = constraints.get("attributes") or {}
    budget = constraints.get("budget")

    attr_text = ", ".join(f"{k}={v}" for k, v in attributes.items()) if attributes else ""
    context_parts = []
    if product_type:
        context_parts.append(f"product_type={product_type}")
    if attr_text:
        context_parts.append(f"attributes={attr_text}")
    for key in ("brand_include", "brand_exclude", "must_have", "nice_to_have"):
        values = constraints.get(key) or []
        if values:
            context_parts.append(f"{key}={', '.join(str(v) for v in values)}")
    if budget:
        context_parts.append(f"budget={budget}")
    context = "; ".join(context_parts) if context_parts else "same product context as previous turn"
    return f"Follow-up request with previous context [{context}]: {user_query}"


def _answer_follow_up_from_previous(user_query: str, previous_response: dict) -> str:
    links = previous_response.get("shortlist", []) or []
    if not links:
        return "I do not have previous product options in context yet. Please ask for products first."

    top_links = links[:3]
    best = top_links[0]
    lines: list[str] = []
    lines.append("Great follow-up. Here is a quick comparison from the latest results:")
    lines.append("")
    for idx, item in enumerate(top_links, start=1):
        title = str(item.get("title", "Untitled result")).strip()
        domain = str(item.get("domain", "")).strip()
        explanation = str(item.get("explanation", "")).strip()
        lines.append(f"{idx}) {title} ({domain})")
        if explanation:
            lines.append(f"   - {explanation}")
    lines.append("")
    lines.append(
        f"Based on the previous shortlist, a strong option to compare first is: "
        f"{best.get('title', 'Top result')} ({best.get('domain', '')})."
    )
    lines.append(
        "Reason: it had the highest combined relevance score in the last search "
        "(intent match, filters, and any personalization boosts shown earlier)."
    )
    lines.append("If you want, I can now refine by price, brand, or style.")
    return "\n".join(lines)


def _build_ui_message(response: dict) -> str:
    if response.get("route") != "shopping":
        return str(response.get("message") or "I can help with product search requests.")

    constraints = response.get("constraints", {}) or {}
    links = response.get("shortlist", []) or []

    product_type = str(constraints.get("product_type") or "product")
    attributes = constraints.get("attributes") or {}
    parse_block = response.get("parse") or {}
    budget_display = parse_block.get("budget_display")
    budget = constraints.get("budget")
    budget_amount = constraints.get("budget_amount")
    budget_currency = constraints.get("budget_currency")

    attr_parts = [f"{k}: {v}" for k, v in attributes.items()]
    attr_text = ", ".join(attr_parts) if attr_parts else "no specific attributes"
    if budget_display:
        budget_text = str(budget_display)
    elif budget_amount is not None and budget_currency:
        budget_text = f"Budget: {budget_amount} {budget_currency}"
    elif budget:
        budget_text = str(budget)
    else:
        budget_text = "no fixed budget"
    brand_include = constraints.get("brand_include") or []
    must_have = constraints.get("must_have") or []
    constraint_bits: list[str] = [attr_text, f"budget: {budget_text}"]
    if brand_include:
        constraint_bits.append(f"brands: {', '.join(str(b) for b in brand_include)}")
    if must_have:
        constraint_bits.append(f"must have: {', '.join(str(m) for m in must_have)}")

    lines: list[str] = []
    agent_message = str(response.get("message") or "").strip()
    clarifications = parse_block.get("clarification_questions") or []
    if agent_message:
        lines.append(agent_message)
        lines.append("")
    elif clarifications:
        lines.append(" ".join(str(q) for q in clarifications))
        lines.append("")

    lines.append(
        f"I found {len(links)} options for {product_type} "
        f"({'; '.join(constraint_bits)})."
    )
    lines.append("")
    lines.append("Top picks:")

    if not links:
        lines.append("- I could not find matching links right now. Please try a more specific query.")
    else:
        for idx, item in enumerate(links[:5], start=1):
            title = str(item.get("title", "Untitled result")).strip()
            domain = str(item.get("domain", "")).strip()
            url = str(item.get("url", "")).strip()
            explanation = str(item.get("explanation", "")).strip()
            why = str(item.get("why_seeing_this", "")).strip()
            lines.append(f"{idx}) {title} ({domain})")
            if explanation:
                lines.append(f"   Relevance: {explanation}")
            if why:
                lines.append(f"   Why you're seeing this: {why}")
            if url:
                lines.append(f"   Link: {url}")
            lines.append("")

    disclaimer = str(response.get("disclaimer", "")).strip()
    if disclaimer:
        lines.append(f"Note: {disclaimer}")

    return "\n".join(lines).strip()


def _shopping_ui_intro(response: dict, agent_message: str) -> str:
    if agent_message:
        return agent_message
    constraints = response.get("constraints", {}) or {}
    product_type = str(constraints.get("product_type") or "products").strip()
    count = len(response.get("shortlist") or [])
    if count:
        return f"Found {count} options for {product_type}."
    return "No matching product links in this response."


def _enrich_shopping_ux(response: dict) -> dict:
    enriched = dict(response)
    agent_message = str(response.get("message") or "").strip()
    shortlist = enriched.get("shortlist") or []
    if enriched.get("route") == "shopping" and shortlist:
        enriched["decision_summary"] = build_decision_summary(enriched)
        enriched["follow_up_chips"] = build_follow_up_chips(enriched)
        enriched["decision_artifact_markdown"] = build_shareable_markdown(enriched)
        enriched["ui_intro"] = _shopping_ui_intro(enriched, agent_message)
    else:
        enriched["decision_summary"] = []
        enriched["follow_up_chips"] = []
        enriched["decision_artifact_markdown"] = ""
        enriched["ui_intro"] = agent_message or str(response.get("message") or "")
    payload_for_text = {**enriched, "message": agent_message}
    enriched["message"] = _build_ui_message(payload_for_text)
    return enriched


def _attach_ui_message(response: dict) -> dict:
    return _enrich_shopping_ux(response)


def _print_chat_timing(
    user_query: str,
    *,
    ttfb_s: float,
    total_s: float,
    route: str = "",
    path: str = "agent",
    outcome: str = "",
) -> None:
    """Log server-side latency to the terminal running the chat app."""
    preview = user_query if len(user_query) <= 72 else f"{user_query[:69]}..."
    route_bit = f" route={route}" if route else ""
    outcome_bit = f" outcome={outcome}" if outcome else ""
    print(
        f"[chat timing] path={path}{route_bit}{outcome_bit} query={preview!r} "
        f"ttfb_s={ttfb_s:.3f} total_s={total_s:.3f}",
        flush=True,
    )


def _persist_chat_request(
    session_id: str,
    user_query: str,
    *,
    ttfb_s: float,
    total_s: float,
    path: str,
    outcome: str,
    route: str = "",
    response: dict | None = None,
    http_status: int = 200,
    error_detail: str | None = None,
    is_follow_up: bool = False,
) -> None:
    shortlist_count = len(response.get("shortlist") or []) if response else None
    record_chat_request(
        session_id=session_id,
        query_text=user_query,
        path=path,
        ttfb_s=ttfb_s,
        total_s=total_s,
        outcome=outcome,
        route=route,
        shortlist_count=shortlist_count,
        http_status=http_status,
        error_detail=error_detail,
        is_follow_up=is_follow_up,
    )
    _print_chat_timing(
        user_query,
        ttfb_s=ttfb_s,
        total_s=total_s,
        route=route,
        path=path,
        outcome=outcome,
    )


def _follow_up_response(user_query: str, previous_response: dict) -> dict:
    response = dict(previous_response)
    response["query"] = user_query
    response["message"] = _answer_follow_up_from_previous(user_query, previous_response)
    return _enrich_shopping_ux(response)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/")
def home() -> str:
    return render_template_string(HTML_PAGE, session_id=_get_session_id())


@app.post("/api/track_event")
def api_track_event():
    payload = request.get_json(silent=True) or {}
    error = record_event(payload)
    if error:
        return jsonify({"error": error}), 400
    return jsonify({"ok": True})


@app.post("/api/preferences")
def api_preferences():
    payload = request.get_json(silent=True) or {}
    session_id = _get_session_id()

    if payload.get("reset"):
        reset_session_preferences(session_id)

    if "enabled" in payload:
        session["personalization_enabled"] = bool(payload["enabled"])

    return jsonify(
        {
            "ok": True,
            "personalization_enabled": _personalization_enabled(),
            "session_id": session_id,
        }
    )


@app.post("/api/chat")
def api_chat():
    t_request = time.perf_counter()
    session_id = _get_session_id()
    rate_error = _check_chat_rate_limit(session_id)
    if rate_error:
        t_now = time.perf_counter()
        _persist_chat_request(
            session_id,
            "",
            ttfb_s=t_now - t_request,
            total_s=t_now - t_request,
            path="rate_limited",
            outcome="rate_limited",
            http_status=429,
            error_detail=rate_error,
        )
        return jsonify({"error": rate_error}), 429

    session_error = _ensure_chat_session_allowed(session_id)
    if session_error:
        t_now = time.perf_counter()
        _persist_chat_request(
            session_id,
            "",
            ttfb_s=t_now - t_request,
            total_s=t_now - t_request,
            path="session_unavailable",
            outcome="session_unavailable",
            http_status=503,
            error_detail=session_error,
        )
        return jsonify({"error": session_error}), 503

    payload = request.get_json(silent=True) or {}
    user_query = str(payload.get("query", "")).strip()
    if not user_query:
        return jsonify({"error": "query is required"}), 400
    if len(user_query) > MAX_QUERY_LENGTH:
        return jsonify({"error": "Query too long"}), 400

    state = _CHAT_STATE.setdefault(session_id, {"last_shopping_response": None})

    previous_response = state.get("last_shopping_response")
    follow_up = _looks_like_follow_up(user_query) and previous_response is not None

    # For compare/recommendation follow-ups, answer directly from prior links.
    if follow_up and _is_compare_or_recommend_query(user_query):
        response = _follow_up_response(user_query, previous_response)
        t_core = time.perf_counter()
        response["session_id"] = session_id
        outcome = classify_outcome(response)
        _persist_chat_request(
            session_id,
            user_query,
            ttfb_s=t_core - t_request,
            total_s=t_core - t_request,
            path="compare_follow_up",
            outcome=outcome,
            route=str(response.get("route", "")),
            response=response,
            is_follow_up=True,
        )
        return jsonify(response)

    query_to_run = (
        _build_contextual_query(user_query, previous_response) if follow_up else user_query
    )

    try:
        response = agent.run(
            query_to_run,
            session_id=session_id,
            personalization_enabled=_personalization_enabled(),
        )
    except SerpApiSearchError as err:
        t_fail = time.perf_counter()
        detail = str(err).strip()
        _persist_chat_request(
            session_id,
            user_query,
            ttfb_s=t_fail - t_request,
            total_s=t_fail - t_request,
            path="search_failed",
            outcome="search_failed",
            http_status=502,
            error_detail=detail,
            is_follow_up=follow_up,
        )
        return (
            jsonify(
                {
                    "error": (
                        "Search failed. Product search is temporarily unavailable. "
                        "Please try again in a moment."
                        + (f" ({detail})" if detail else "")
                    ),
                    "search_failed": True,
                    "detail": detail,
                }
            ),
            502,
        )
    except Exception as err:  # pragma: no cover
        t_fail = time.perf_counter()
        _persist_chat_request(
            session_id,
            user_query,
            ttfb_s=t_fail - t_request,
            total_s=t_fail - t_request,
            path="error",
            outcome="error",
            http_status=500,
            error_detail=str(err),
            is_follow_up=follow_up,
        )
        return jsonify({"error": f"Unexpected error: {err}"}), 500

    t_core = time.perf_counter()
    response = _attach_ui_message(response)
    if response.get("route") == "shopping" and response.get("shortlist"):
        state["last_shopping_response"] = response

    response["session_id"] = session_id
    t_done = time.perf_counter()
    outcome = classify_outcome(response)
    _persist_chat_request(
        session_id,
        user_query,
        ttfb_s=t_core - t_request,
        total_s=t_done - t_request,
        path="agent",
        outcome=outcome,
        route=str(response.get("route", "")),
        response=response,
        is_follow_up=follow_up,
    )
    return jsonify(response)


def main() -> None:
    settings.validate()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
