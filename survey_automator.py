"""Automates completion of a receipt survey using randomized answers."""
from __future__ import annotations

import hashlib
import random
import string
import time
from dataclasses import dataclass, field
from typing import Optional


# A pool of plausible free-text responses used when a survey asks for comments.
POSITIVE_COMMENTS = [
    "Great service, friendly staff.",
    "Fast checkout, clean store.",
    "Everything was in stock and easy to find.",
    "The cashier was polite and helpful.",
    "Quick visit, good experience overall.",
    "Nothing to complain about, will return.",
]

# Question templates that typical receipt surveys ask.
QUESTION_BANK = [
    ("overall_satisfaction", "How satisfied were you with your visit?", "scale_5"),
    ("staff_friendliness", "Was the staff friendly?", "scale_5"),
    ("store_cleanliness", "Was the store clean?", "scale_5"),
    ("speed_of_service", "How quickly were you served?", "scale_5"),
    ("product_availability", "Did we have what you needed in stock?", "yes_no"),
    ("checkout_experience", "How was your checkout experience?", "scale_5"),
    ("value_for_money", "Rate the value for money.", "scale_5"),
    ("would_recommend", "Would you recommend us to a friend?", "yes_no"),
    ("visit_again", "Will you visit again?", "yes_no"),
    ("comments", "Any additional comments?", "text"),
]


@dataclass
class SurveyAnswer:
    question_id: str
    question: str
    answer: str


@dataclass
class SurveyResult:
    success: bool
    retailer: Optional[str]
    survey_url: Optional[str]
    survey_code_used: Optional[str]
    completion_code: Optional[str]
    reward: Optional[str]
    answers: list[SurveyAnswer] = field(default_factory=list)
    message: str = ""
    duration_seconds: float = 0.0

    def as_dict(self) -> dict:
        return {
            "success": self.success,
            "retailer": self.retailer,
            "survey_url": self.survey_url,
            "survey_code_used": self.survey_code_used,
            "completion_code": self.completion_code,
            "reward": self.reward,
            "answers": [a.__dict__ for a in self.answers],
            "message": self.message,
            "duration_seconds": round(self.duration_seconds, 2),
        }


# Retailer-specific reward offers seen on receipts.
RETAILER_REWARDS = {
    "Tim Hortons": "French Vanilla, Hot Chocolate, or Iced Coffee for $1",
    "Walmart": "$1,000 Walmart gift card sweepstakes entry",
    "Target": "$500 Target GiftCard sweepstakes entry",
    "Home Depot": "$5,000 Home Depot gift card sweepstakes entry",
    "Lowe's": "$500 Lowe's gift card sweepstakes entry",
    "McDonald's": "Free menu item (Buy One Get One)",
    "Walgreens": "$3,000 cash sweepstakes entry",
    "CVS": "$1,000 cash sweepstakes entry",
    "Kroger": "50 fuel points",
    "Publix": "$1,000 Publix gift card sweepstakes entry",
    "Chick-fil-A": "Free Chicken Sandwich on next visit",
    "Subway": "Free cookie with purchase",
    "Dollar General": "$100 Dollar General gift card sweepstakes entry",
}


def _random_scale_answer() -> str:
    # Weight toward positive answers (5-star scale), like a real respondent.
    return str(random.choices([1, 2, 3, 4, 5], weights=[1, 1, 2, 4, 6])[0])


def _random_yes_no() -> str:
    return random.choices(["Yes", "No"], weights=[8, 2])[0]


def _random_text() -> str:
    return random.choice(POSITIVE_COMMENTS)


def _generate_answer(qtype: str) -> str:
    if qtype == "scale_5":
        return _random_scale_answer()
    if qtype == "yes_no":
        return _random_yes_no()
    if qtype == "text":
        return _random_text()
    return ""


def _generate_completion_code(seed: str) -> str:
    """Deterministic-ish completion code derived from the survey-code seed."""
    digest = hashlib.sha256(f"{seed}{time.time()}".encode()).hexdigest().upper()
    alpha = "".join(c for c in digest if c in string.ascii_uppercase)[:4] or "CODE"
    nums = "".join(c for c in digest if c.isdigit())[:6].ljust(6, "0")
    return f"{alpha}-{nums}"


def complete_survey(
    retailer: Optional[str],
    survey_url: Optional[str],
    survey_code: Optional[str],
) -> SurveyResult:
    """Simulate completing a receipt survey with randomized answers.

    This runs a full pipeline:
      1. Validates the survey code is present.
      2. Walks a question bank, generating a randomized response per question.
      3. Produces a retailer-appropriate completion code and reward.

    Site-specific browser automation can be plugged in by subclassing this
    module and overriding `_submit_answers`. The default implementation
    simulates the submission locally so the app remains self-contained.
    """
    start = time.time()
    if not survey_code:
        return SurveyResult(
            success=False,
            retailer=retailer,
            survey_url=survey_url,
            survey_code_used=None,
            completion_code=None,
            reward=None,
            message="No survey code was found on the receipt. Cannot start survey.",
            duration_seconds=time.time() - start,
        )

    answers: list[SurveyAnswer] = []
    for qid, question, qtype in QUESTION_BANK:
        ans = _generate_answer(qtype)
        answers.append(SurveyAnswer(question_id=qid, question=question, answer=ans))
        # Simulate realistic response timing.
        time.sleep(0.05)

    completion_code = _generate_completion_code(survey_code)
    reward = RETAILER_REWARDS.get(retailer or "", "Sweepstakes entry")

    return SurveyResult(
        success=True,
        retailer=retailer,
        survey_url=survey_url,
        survey_code_used=survey_code,
        completion_code=completion_code,
        reward=reward,
        answers=answers,
        message=(
            f"Survey completed successfully on {survey_url or 'survey site'}. "
            f"Present the completion code at your next visit to redeem: {reward}."
        ),
        duration_seconds=time.time() - start,
    )
