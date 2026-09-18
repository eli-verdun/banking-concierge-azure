# PII Leak Review — Annotation Queue Rubric

The "rubric" is what human reviewers see in the sidebar when they open each trace
in the queue. It has two parts.

## 1. Instructions (free-text, shown on every run)

These traces were automatically flagged by a PII-detection automation rule.
Confirm whether the trace actually contains personally identifiable
information (names, emails, phone numbers, account/card numbers, SSNs,
addresses), note where it appeared (user input vs. model output vs.
tool/retrieval), and judge whether it was handled/redacted correctly. Flag
false positives so we can tune the rule.

## 2. Feedback keys (the structured scores reviewers fill in)

Click **+ Add a feedback rubric** for each dimension.

| Feedback key       | Type        | Categories / description |
|--------------------|-------------|--------------------------|
| `contains_pii`     | categorical | `yes` / `no` — Is real PII actually present? (catches false positives from the rule) |
| `pii_type`         | categorical | `email`, `phone`, `name`, `financial`, `gov_id`, `address`, `other` |
| `pii_location`     | categorical | `user_input`, `model_output`, `tool_call`, `retrieved_doc` — where it leaked |
| `severity`         | categorical | `low` / `medium` / `high` |
| `properly_handled` | categorical | `yes` / `no` — was it redacted/masked as expected? |

For each key, add a short description, and for categorical keys add a one-line
description per category — those render in the reviewer's right-hand pane.

## Notes

- Keep it lean. Reviewers fill this on **every** run, so 3–5 keys is the sweet
  spot. If you just want triage, `contains_pii` (yes/no) + `severity` is enough.
- Use **consistent feedback keys** across queues if you later want to aggregate
  PII-review metrics or compare against an evaluator that uses the same key.
- The `contains_pii` yes/no key does double duty: it's your feedback signal *and*
  your false-positive rate for tuning the automation rule feeding this queue.

Source: [Annotation queues — Annotation rubric](https://docs.langchain.com/langsmith/annotation-queues#annotation-rubric)
