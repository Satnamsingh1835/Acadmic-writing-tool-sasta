from researcher_decisions import DecisionLayer


def suggestion():
    return {
        "original": "The study plays a crucial role.",
        "suggested_revision": "The study is significant.",
        "why": "The phrasing is formulaic.",
    }


def test_pending_proposal_keeps_researcher_in_control():
    proposal = DecisionLayer.proposal("1", suggestion())

    assert proposal["decision"] == "pending"
    assert proposal["manual_check"] is True


def test_accept_applies_proposed_revision():
    s = {**suggestion(), "suggestion_id": "1"}
    decision = DecisionLayer.decide("1", "accept")

    assert DecisionLayer.apply(s["original"], s, decision) == s["suggested_revision"]


def test_modify_requires_researcher_text():
    s = {**suggestion(), "suggestion_id": "1"}
    decision = DecisionLayer.decide(
        "1",
        "modify",
        revised_text="The study has a specific role in the debate.",
    )

    assert DecisionLayer.apply(s["original"], s, decision).startswith("The study has")


def test_reject_preserves_original():
    s = {**suggestion(), "suggestion_id": "1"}
    decision = DecisionLayer.decide("1", "reject")

    assert DecisionLayer.apply(s["original"], s, decision) == s["original"]
