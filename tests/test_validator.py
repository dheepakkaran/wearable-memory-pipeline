from wmp.batch import rule_extract, validate

CAPS = [{"capture_id": "m-001", "start_s": 0, "text": "Okay so the industrial designer will look at the working design, right?"},
        {"capture_id": "m-002", "start_s": 30, "text": "And I'll send the minutes after the meeting."}]


def item(quote, cid="m-001", text="Industrial designer works on the working design."):
    return {"kind": "commitment", "text": text, "owner": "", "due": "", "evidence_quote": quote, "capture_id": cid}


def test_exact_quote_passes_even_with_punctuation_differences():
    good, bad = validate([item("the industrial designer will look at the working design")], CAPS)
    assert len(good) == 1 and not bad


def test_invented_quote_fails():
    good, bad = validate([item("the designer will build a prototype by Monday")], CAPS)
    assert not good and len(bad) == 1


def test_wrong_capture_id_fails():
    _, bad = validate([item("I'll send the minutes after the meeting")], CAPS)
    assert len(bad) == 1


def test_rule_baseline_finds_promise():
    assert any("send the minutes" in c["text"] for c in rule_extract(CAPS))
