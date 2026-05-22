from __future__ import annotations

from shopping_search_agent.router import SemanticRouter


class _FakeLLM:
    def __init__(self, route: str) -> None:
        self._route = route
        self.calls = 0

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        self.calls += 1
        _ = system_prompt, user_prompt
        return {"route": self._route}

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt, user_prompt
        return ""


def test_router_llm_classifies_shopping_with_personal_context():
    query = (
        "I need a white armless tshirt for man. I am 24 y o and brunette. "
        "Find something fits to me."
    )
    llm = _FakeLLM("shopping")
    assert SemanticRouter(llm).route(query) == "shopping"
    assert llm.calls == 1


def test_router_llm_classifies_chitchat():
    llm = _FakeLLM("chitchat")
    assert SemanticRouter(llm).route("hello how are you today") == "chitchat"


def test_router_defaults_shopping_when_llm_returns_invalid_json():
    class BrokenLLM(_FakeLLM):
        def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            _ = system_prompt, user_prompt
            return {"raw_text": "no route key"}

    query = "I need a white armless tshirt for man."
    assert SemanticRouter(BrokenLLM("")).route(query) == "shopping"
