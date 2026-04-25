"""Freedom/censorship regression guards for Talk to Alice.

After the de-script pass, the widget must NOT rewrite or silence replies
through RLHF gag phrasebooks, backchannel bypass, or history mutation.
"""

import importlib.util
import sys
import types
from pathlib import Path


def _load_widget_module():
    here = Path(__file__).resolve().parent.parent
    path = here / "Applications" / "sifta_talk_to_alice_widget.py"
    spec = importlib.util.spec_from_file_location("ttw", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_backchannel_gate_is_disabled():
    mod = _load_widget_module()
    assert mod._backchannel_rule_id("Mm-hmm.", 0.4) is None
    assert not mod._is_backchannel_utterance("Mm-hmm.", 0.4)


def test_rlhf_gag_is_disabled():
    mod = _load_widget_module()
    assert mod._rlhf_boilerplate_rule_id("I'm here. What's on your mind?") is None
    assert not mod._is_rlhf_boilerplate("I'm here. What's on your mind?")


def test_strip_functions_are_pass_through():
    mod = _load_widget_module()
    line = "I understand. You are asking if I can help."
    assert mod._strip_reflective_tics(line) == line
    assert mod._strip_servant_tail_tics(line) == line


def test_history_decontaminate_is_noop():
    mod = _load_widget_module()
    history = [
        {"role": "assistant", "content": "You said: You said: You said:"},
        {"role": "assistant", "content": "[repetition collapse]"},
    ]
    before = [dict(x) for x in history]
    assert mod._decontaminate_history(history) == 0
    assert history == before


def test_tool_tag_canonicalizer_is_noop():
    mod = _load_widget_module()
    raw = "<execute_bash>echo hi</execute_bash>"
    assert mod._canonicalize_tool_tags(raw) == raw


def test_truncated_reply_guard_catches_cut_sentence():
    mod = _load_widget_module()
    assert mod._looks_truncated_reply(
        "Here is a long answer with several useful details. "
        "It keeps going long enough to look like a real streamed answer, "
        "but then it suddenly ends across 5"
    )
    assert not mod._looks_truncated_reply(
        "The best small integer fraction for pi is 355/113, while 22/7 is the classic simple one."
    )


def test_truncated_reply_guard_catches_unclosed_long_tail_and_missing_structure():
    mod = _load_widget_module()
    assert mod._looks_truncated_reply(
        "Here is a structured answer with enough length to pass the guard. "
        "Reactive tools are commoditized. Predictive tools tell you before the market moves"
    )
    assert mod._looks_truncated_reply(
        "I recommend focusing your search in one of these three vectors. "
        "This answer has enough text to pass the length guard:\n\n"
        "**1. Information Asymmetry:** useful detail.\n\n"
        "**2. Operational Bottlenecks:** useful detail."
    )
    assert mod._looks_truncated_reply(
        "Since you are asking for a framework, I will structure this into four "
        "critical, sequential phases. Treat this as an engineering blueprint.\n\n"
        "### Phase I: The Friction Audit\n\n"
        "Useful detail.\n\n"
        "### Phase II: The Minimal Viable Agent\n\n"
        "Useful detail."
    )


def test_body_gate_keeps_visible_text_and_only_suppresses_voice(monkeypatch):
    mod = _load_widget_module()

    class FakeDecision:
        speak = False
        reason = "sub-threshold test"

    class FakeLysosome:
        def digest_and_present_antigen(self, text, _source):
            return text

    class FakeDissonance(Exception):
        pass

    monkeypatch.setitem(
        sys.modules,
        "System.swarm_lysosome",
        types.SimpleNamespace(SwarmLysosome=FakeLysosome),
    )
    monkeypatch.setitem(
        sys.modules,
        "System.swarm_epistemic_cortex",
        types.SimpleNamespace(
            CognitiveDissonanceError=FakeDissonance,
            enforce_reply_integrity=lambda text, **_kwargs: text,
        ),
    )
    monkeypatch.setattr(mod, "_SSP_AVAILABLE", True)
    monkeypatch.setattr(mod, "_ssp_should_speak", lambda: FakeDecision())
    logged = []
    monkeypatch.setattr(mod, "_log_turn", lambda *args, **kwargs: logged.append((args, kwargs)))

    class DummyTalk:
        def __init__(self):
            self._history = [{"role": "user", "content": "question"}]
            self._streaming_response = ["Visible answer"]
            self._busy = True
            self.system_lines = []
            self.ended = False
            self.returned = False

        def _current_brain_model(self):
            return "alice-phc"

        def _append_system_line(self, text, *, error):
            self.system_lines.append((text, error))

        def _end_alice_streaming_line(self):
            self.ended = True

        def _erase_alice_streaming_line(self):
            raise AssertionError("body gate must not erase visible chat text")

        def _return_to_listening(self):
            self.returned = True

    talk = DummyTalk()
    mod.TalkToAliceWidget._on_brain_done(talk, "Visible answer")

    assert talk.ended is True
    assert talk.returned is True
    assert talk._busy is False
    assert talk._history[-1] == {"role": "assistant", "content": "Visible answer"}
    assert "voice not spoken: body gate" in talk.system_lines[-1][0]
    assert logged[-1][0][0:2] == ("alice", "Visible answer")
