"""Bilingual, server-owned strings keyed by message_key / a fixed code.

These never pass through the LLM. In particular DISCLAIMER is injected by
the API layer as its own response field, never composed by the model —
a model that writes its own disclaimer is a model that can drop it.
"""

from __future__ import annotations

Locale = str  # "it" | "en"

DISCLAIMER: dict[Locale, str] = {
    "it": (
        "Questo strumento fornisce stime informative basate su formule "
        "generali e non sostituisce il parere di un medico o di un "
        "nutrizionista qualificato. Non è pensato per diagnosi, terapie o "
        "gestione di condizioni cliniche."
    ),
    "en": (
        "This tool provides informational estimates based on general "
        "formulas and does not replace the advice of a physician or a "
        "qualified nutritionist. It is not intended for diagnosis, "
        "treatment, or management of clinical conditions."
    ),
}

NOT_IN_SOURCES: dict[Locale, str] = {
    "it": (
        "Non ho trovato, tra le fonti che conosco, informazioni "
        "sufficientemente rilevanti per rispondere con sicurezza a questa "
        "domanda."
    ),
    "en": (
        "I couldn't find sufficiently relevant information in my sources "
        "to answer this question with confidence."
    ),
}

GUARDRAIL_MESSAGES: dict[str, dict[Locale, str]] = {
    "guardrail.age_child": {
        "it": "Questo strumento è pensato per adulti; per un bambino/a è necessario il parere di un pediatra.",
        "en": "This tool is designed for adults; a child needs guidance from a pediatrician.",
    },
    "guardrail.age_minor": {
        "it": "Per un minorenne le formule di questo motore non sono validate: posso rispondere a domande generali, ma non generare un piano o dei target personalizzati.",
        "en": "This engine's formulas aren't validated for minors: I can answer general questions, but I won't generate a personalized plan or targets.",
    },
    "guardrail.age_implausible": {
        "it": "L'età indicata non sembra plausibile: verifica il valore inserito.",
        "en": "The age provided doesn't look plausible: please check the value.",
    },
    "guardrail.age_elderly": {
        "it": "Per età superiori a 90 anni le formule standard sono meno affidabili: prendi i target con maggiore cautela.",
        "en": "For ages above 90 the standard formulas are less reliable: treat these targets with extra caution.",
    },
    "guardrail.height_range": {
        "it": "L'altezza indicata sembra fuori da un intervallo plausibile.",
        "en": "The height provided looks outside a plausible range.",
    },
    "guardrail.weight_range": {
        "it": "Il peso indicato sembra fuori da un intervallo plausibile.",
        "en": "The weight provided looks outside a plausible range.",
    },
    "guardrail.bmi_severe_underweight": {
        "it": "Il tuo BMI è molto basso: per la tua sicurezza non genero un piano alimentare automatico. Ti consiglio di parlarne con un medico.",
        "en": "Your BMI is very low: for your safety I won't generate an automated meal plan. Please talk to a doctor.",
    },
    "guardrail.bmi_underweight": {
        "it": "Il tuo BMI è sotto la soglia di normopeso: ho impostato l'obiettivo su mantenimento invece di un deficit calorico.",
        "en": "Your BMI is below the normal-weight threshold: I've set the goal to maintenance instead of a calorie deficit.",
    },
    "guardrail.bmi_class_iii": {
        "it": "Con un BMI in questa fascia, un percorso alimentare è più sicuro con supervisione clinica: ho limitato il deficit calorico per cautela.",
        "en": "With a BMI in this range, a nutrition plan is safer with clinical supervision: I've capped the calorie deficit as a precaution.",
    },
    "guardrail.goal_conflict_deficit": {
        "it": "Il tuo BMI non è compatibile con un deficit calorico: ho impostato l'obiettivo su mantenimento.",
        "en": "Your BMI isn't compatible with a calorie deficit: I've set the goal to maintenance.",
    },
    "guardrail.condition_screen": {
        "it": "Hai menzionato una condizione per cui un piano alimentare automatico non è appropriato senza supervisione medica. Posso comunque rispondere a domande generali basate sulle fonti.",
        "en": "You mentioned a condition for which an automated meal plan isn't appropriate without medical supervision. I can still answer general questions based on my sources.",
    },
    "guardrail.deficit_relaxed_for_floors": {
        "it": "Il deficit calorico richiesto avrebbe reso impossibile rispettare i minimi di proteine e grassi: l'ho ridotto per mantenerli.",
        "en": "The requested calorie deficit would have made it impossible to meet the protein and fat floors: I've reduced it to keep them.",
    },
}


def guardrail_message(message_key: str, locale: Locale) -> str:
    entry = GUARDRAIL_MESSAGES.get(message_key)
    if entry is None:
        return message_key
    return entry.get(locale, entry.get("it", message_key))
