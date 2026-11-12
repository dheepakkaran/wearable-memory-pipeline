"""PII redaction before anything is stored or sent to an LLM (Presidio, local).

v1: spaCy small model + Presidio defaults (results/pii_v1.json).
v2 (current): spaCy medium model for names + a plain phone pattern. Presidio's built-in phone check rejects
numbers it cannot validate (unreal area codes), but a number a person speaks aloud is private either way.
"""
import os
from functools import lru_cache

ENTITIES = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "US_SSN", "IP_ADDRESS"]
SPACY = os.getenv("WMP_SPACY", "en_core_web_md")
PHONE = r"(?:\+?1[ .-]?)?\(?\b\d{3}\)?[ .-]?\d{3}[ .-]\d{4}\b"


@lru_cache(maxsize=1)
def _engines():
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine

    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": SPACY}]}).create_engine()
    an = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    if SPACY != "en_core_web_sm":
        an.registry.add_recognizer(PatternRecognizer(supported_entity="PHONE_NUMBER", name="spoken_phone",
                                                     patterns=[Pattern("phone", PHONE, 0.6)]))
    return an, AnonymizerEngine()


def find(text: str):
    analyzer, _ = _engines()
    return analyzer.analyze(text=text, language="en", entities=ENTITIES, score_threshold=0.4)


def redact(text: str) -> tuple[str, int]:
    """Return (text with <ENTITY> placeholders, number of spans replaced)."""
    if not text.strip():
        return text, 0
    analyzer, anonymizer = _engines()
    hits = find(text)
    if not hits:
        return text, 0
    return anonymizer.anonymize(text=text, analyzer_results=hits).text, len(hits)
