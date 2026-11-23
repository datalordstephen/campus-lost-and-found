"""Scoring-rule plumbing for ownership verification.

The verification pilot (13 owners, 26 impostor claims; thesis Section 4.5.9)
showed that the original forward rule rejects every genuine owner, so the app
now defaults to the reverse rule: the claim must entail a recorded detail.

The first group of tests needs no model: the NLI call is replaced by a fake
that records which (premise, hypothesis) pairs were asked for. The last test
loads the real checkpoint and is marked slow.
"""

from __future__ import annotations

import pytest

from backend import verification

SECRET = "Initials O.H on the back. A just do it sticker inside the cover"


@pytest.fixture
def fake_nli(monkeypatch):
    """Score each pair by a lookup table and record the pairs asked for."""
    calls: list[tuple[str, str]] = []
    table: dict[tuple[str, str], float] = {}

    def fake(pairs):
        calls.extend(pairs)
        return [table.get(pair, 0.01) for pair in pairs]

    monkeypatch.setattr(verification, "verify_claims", fake)
    return calls, table


def test_split_details_keeps_whole_and_each_sentence():
    details = verification.split_details(SECRET)
    assert details[0] == SECRET
    assert "Initials O.H on the back" in details  # the dot in "O.H" does not split
    assert "A just do it sticker inside the cover" in details
    assert len(details) == 3


def test_split_details_drops_fragments_and_duplicates():
    assert verification.split_details("blue sticker. blue sticker. x") == [
        "blue sticker. blue sticker. x",
        "blue sticker",
    ]
    assert verification.split_details("one detail only") == ["one detail only"]


def test_default_rule_is_reverse(monkeypatch):
    monkeypatch.delenv("NLI_RULE", raising=False)
    assert verification.verification_rule() == "reverse"


def test_unknown_rule_falls_back_to_reverse(monkeypatch):
    monkeypatch.setenv("NLI_RULE", "sideways")
    assert verification.verification_rule() == "reverse"


def test_reverse_puts_the_claim_first_and_takes_the_best_detail(monkeypatch, fake_nli):
    calls, table = fake_nli
    claim = "my calculator has a just do it sticker"
    table[(claim, "A just do it sticker inside the cover")] = 0.91
    monkeypatch.setenv("NLI_RULE", "reverse")

    score = verification.verify_claim(SECRET, claim)

    assert score == pytest.approx(0.91)
    assert all(premise == claim for premise, _ in calls), "claim must be the premise"
    assert {h for _, h in calls} == set(verification.split_details(SECRET))


def test_forward_rule_is_still_available(monkeypatch, fake_nli):
    calls, table = fake_nli
    table[(SECRET, "anything")] = 0.8
    monkeypatch.setenv("NLI_RULE", "forward")

    assert verification.verify_claim(SECRET, "anything") == pytest.approx(0.8)
    assert calls == [(SECRET, "anything")]


def test_empty_inputs_score_zero_under_both_rules(monkeypatch, fake_nli):
    calls, _ = fake_nli
    for rule in ("forward", "reverse"):
        monkeypatch.setenv("NLI_RULE", rule)
        assert verification.verify_claim("", "a claim") == 0.0
        assert verification.verify_claim("a detail", "  ") == 0.0
    assert calls == []


@pytest.mark.slow
def test_reverse_rule_on_pilot_style_claims(capsys):
    """Real checkpoint. Prints the scores; asserts only the clear-cut cases.

    The pilot found the reverse rule better but far from reliable, so this
    test records behaviour rather than promising a pass rate.
    """
    verification.load_model()
    cases = [
        ("owner names a recorded detail",
         "A black casio calculator with my initials at the back and a just do it sticker", None),
        ("impostor contradicts", "it has no stickers and nothing written on it", False),
        ("impostor, wrong item", "it is a red umbrella with a wooden handle", False),
    ]
    with capsys.disabled():
        print()
        for label, claim, expected in cases:
            score = verification.verify_claim_reverse(SECRET, claim)
            print(f"  {label:<32} reverse {score:.3f}")
            if expected is False:
                assert not verification.passes(score), f"{label!r} approved at {score:.3f}"
