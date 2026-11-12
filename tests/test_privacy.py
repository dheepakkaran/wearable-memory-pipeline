from wmp.privacy import redact


def test_email_and_phone_removed():
    out, n = redact("email me at maria.lopez@gmail.com or call (617) 555-0142 tomorrow")
    assert "maria.lopez@gmail.com" not in out and "555-0142" not in out and n >= 2


def test_person_removed():
    out, _ = redact("so I'll send the draft to Priya Raman before Friday")
    assert "Priya" not in out and "<PERSON>" in out


def test_plain_text_untouched():
    s = "we should make the remote control yellow and easy to find"
    assert redact(s) == (s, 0)
