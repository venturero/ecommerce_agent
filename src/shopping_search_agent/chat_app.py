from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, render_template_string, request, session

from .agent import ShoppingSearchAgent
from .config import Settings
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
      form { display: flex; gap: 10px; margin-top: 14px; }
      input { flex: 1; padding: 10px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 14px; }
      button { padding: 10px 14px; border: 0; border-radius: 8px; background: #2563eb; color: #fff; cursor: pointer; }
      button:disabled { background: #94a3b8; cursor: not-allowed; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <h1>Shopping Search Agent Chat</h1>
      <p class="note">Ask shopping requests and get a conversational answer with recommendations.</p>
      <div id="chat" class="chat"></div>
      <form id="form">
        <input id="query" placeholder="I need waterproof running shoes for women under $120" />
        <button id="send" type="submit">Send</button>
      </form>
    </div>
    <script>
      const chat = document.getElementById("chat");
      const form = document.getElementById("form");
      const query = document.getElementById("query");
      const send = document.getElementById("send");

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

      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = query.value.trim();
        if (!text) return;
        appendMessage("user", text);
        query.value = "";
        send.disabled = true;
        try {
          const res = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({query: text})
          });
          const data = await res.json();
          if (!res.ok) {
            appendMessage("bot", data.error || "Request failed.");
          } else {
            appendMessage("bot", data.message || "No response.");
          }
        } catch (err) {
          appendMessage("bot", `Error: ${String(err)}`);
        } finally {
          send.disabled = false;
          query.focus();
        }
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


def _get_session_id() -> str:
    session_id = session.get("session_id")
    if not session_id:
        session_id = str(uuid4())
        session["session_id"] = session_id
    return str(session_id)


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
        f"My top recommendation right now is: {best.get('title', 'Top result')} "
        f"({best.get('domain', '')})."
    )
    lines.append("Reason: it ranked highest in the previous result set for your stated intent.")
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
            lines.append(f"{idx}) {title} ({domain})")
            if explanation:
                lines.append(f"   Why: {explanation}")
            if url:
                lines.append(f"   Link: {url}")
            lines.append("")

    disclaimer = str(response.get("disclaimer", "")).strip()
    if disclaimer:
        lines.append(f"Note: {disclaimer}")

    return "\n".join(lines).strip()


def _attach_ui_message(response: dict) -> dict:
    enriched = dict(response)
    enriched["message"] = _build_ui_message(response)
    return enriched


def _follow_up_response(user_query: str, previous_response: dict) -> dict:
    response = dict(previous_response)
    response["query"] = user_query
    response["message"] = _answer_follow_up_from_previous(user_query, previous_response)
    return response


@app.get("/")
def home() -> str:
    return render_template_string(HTML_PAGE)


@app.post("/api/chat")
def api_chat():
    session_id = _get_session_id()
    state = _CHAT_STATE.setdefault(session_id, {"last_shopping_response": None})

    payload = request.get_json(silent=True) or {}
    user_query = str(payload.get("query", "")).strip()
    if not user_query:
        return jsonify({"error": "query is required"}), 400

    previous_response = state.get("last_shopping_response")
    follow_up = _looks_like_follow_up(user_query) and previous_response is not None

    # For compare/recommendation follow-ups, answer directly from prior links.
    if follow_up and _is_compare_or_recommend_query(user_query):
        return jsonify(_follow_up_response(user_query, previous_response))

    query_to_run = (
        _build_contextual_query(user_query, previous_response) if follow_up else user_query
    )

    try:
        response = agent.run(query_to_run)
    except SerpApiSearchError as err:
        return jsonify({"error": f"Search API error: {err}"}), 502
    except Exception as err:  # pragma: no cover
        return jsonify({"error": f"Unexpected error: {err}"}), 500

    response = _attach_ui_message(response)
    if response.get("route") == "shopping" and response.get("shortlist"):
        state["last_shopping_response"] = response

    return jsonify(response)


def main() -> None:
    settings.validate()
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
