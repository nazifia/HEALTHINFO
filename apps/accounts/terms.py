"""The Healthcare Terms and Conditions a prescriber agrees to before a seat is
opened for them. One copy, served to both clients (GET /api/auth/register/terms/)
so the text on the screen is the text on record.

Bump ``version`` when a clause changes; ``User.terms_accepted_at`` says when a
prescriber agreed, and the version says to what.
"""

PRESCRIBER_TERMS = {
    "title": "Healthcare Terms and Conditions for Prescribers",
    "version": "2026-09",
    "clauses": [
        "I hold a current, valid licence to practise, issued by the regulatory "
        "body for my cadre, and the licence number on this account is mine.",
        "I will prescribe, order and record care only within the scope of "
        "practice my licence and cadre allow.",
        "Every prescription, consultation and record written under my "
        "credentials is my professional responsibility, and I will keep my "
        "sign-in details to myself.",
        "I will keep patient information confidential and use it only for "
        "the care of that patient, as the Nigeria Data Protection Act and my "
        "professional code require.",
        "I will keep records accurate, complete and timely, and I will not "
        "alter or delete a record to hide an error.",
        "I will order controlled drugs only where clinically justified and in "
        "line with the National Drug Law Enforcement Agency and Pharmacists "
        "Council regulations.",
        "I understand my activity on this platform is logged for audit and "
        "may be shared with a health authority or regulator on lawful request.",
        "The platform supports, and does not replace, my clinical judgement; "
        "responsibility for a clinical decision stays with me.",
        "I will tell the platform administrator at once if my licence is "
        "suspended, restricted or withdrawn.",
    ],
}
