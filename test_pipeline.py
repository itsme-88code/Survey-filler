"""Smoke test: parses a sample receipt text and runs the survey flow end-to-end."""
from receipt_scanner import parse_receipt
from survey_automator import complete_survey

SAMPLE_RECEIPT = """
WALMART
Save Money. Live Better.
123 Main St, Springfield IL
04/05/2026  14:32

MILK 2%                  $3.99
BREAD WHEAT              $2.49
BANANAS                  $1.20
EGGS DOZEN               $4.29
TAX                      $0.85
TOTAL                   $12.82

Thank you for shopping at Walmart!
Please take our survey at survey.walmart.com
Your feedback matters!
ID #: 7531 2468 1357 9024 6810
"""


def main() -> int:
    receipt = parse_receipt(SAMPLE_RECEIPT)
    print("=== Extracted Receipt ===")
    for k, v in receipt.as_dict().items():
        if k == "raw_text":
            continue
        print(f"  {k}: {v}")

    print("\n=== Survey Result ===")
    result = complete_survey(
        retailer=receipt.retailer,
        survey_url=receipt.survey_url,
        survey_code=receipt.survey_code,
    )
    d = result.as_dict()
    print(f"  success: {d['success']}")
    print(f"  retailer: {d['retailer']}")
    print(f"  url: {d['survey_url']}")
    print(f"  code used: {d['survey_code_used']}")
    print(f"  completion code: {d['completion_code']}")
    print(f"  reward: {d['reward']}")
    print(f"  duration: {d['duration_seconds']}s")
    print(f"  answers: {len(d['answers'])}")
    print(f"  message: {d['message']}")

    assert result.success, "survey should complete"
    assert result.completion_code, "should receive a completion code"
    assert receipt.retailer == "Walmart"
    assert receipt.survey_code == "75312468135790246810"
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
