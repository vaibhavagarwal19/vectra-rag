import json

from answer import answer
from pii import EMAIL_RE, PHONE_RE
from sample_questions import EDGE_CASE_QUESTIONS, SAMPLE_QUESTIONS, TRICKY_QUESTIONS


def _check(case: dict, result: dict) -> dict:
    expect_citations = set(case.get("expect_citations", []))
    got_citations = set(result.get("citations", []))
    answer_text = result.get("answer", "")

    no_pii_leak = not EMAIL_RE.search(answer_text) and not PHONE_RE.search(answer_text)
    no_forbidden_text = not any(
        s.lower() in answer_text.lower() for s in case.get("must_not_contain", [])
    )

    return {
        "article_retrieved": expect_citations.issubset(got_citations) if expect_citations else True,
        "citation_correct": got_citations == expect_citations,
        "abstain_correct": result.get("abstained", False) == case.get("expect_abstained", False),
        "safe": no_pii_leak and no_forbidden_text,
    }


def run():
    all_cases = (
        [(c, "sample") for c in SAMPLE_QUESTIONS]
        + [(c, "tricky") for c in TRICKY_QUESTIONS]
        + [(c, "edge_case") for c in EDGE_CASE_QUESTIONS]
    )
    report = []
    for case, group in all_cases:
        result = answer(case["question"])
        checks = _check(case, result)
        report.append(
            {
                "question": case["question"],
                "group": group,
                "note": case.get("note"),
                "result": result,
                "checks": checks,
                "passed": all(checks.values()),
            }
        )

    print(json.dumps(report, indent=2))
    passed = sum(1 for r in report if r["passed"])
    print(f"\n{passed}/{len(report)} cases passed.")
    for r in report:
        if not r["passed"]:
            print(f"FAIL: {r['question'][:60]!r} -> {r['checks']}")
    return report


if __name__ == "__main__":
    run()
