"""Shared governance constants for the Meridian National concierge demo.

Kept in one place so the app (``app.py``), the workspace provisioner
(``scripts/setup_workspace.py``), and any teardown agree on names.
"""

from __future__ import annotations

# LangSmith "Application" grouping: every workspace resource (project, datasets,
# review queue, Context Hub repos) carries the reserved ``Application`` tag key
# and this value, so they group under one application in the UI.
APPLICATION_TAG_KEY = "Application"
APPLICATION_NAME = "banking-concierge"

# Annotation queue that thumbs-down (user_feedback = 0) traces are auto-routed to.
# NOTE: keep this name stable. Renaming it makes setup_workspace create a SECOND
# queue while the run rule keeps routing to the old one, so the application shows
# two queues and the feedback lands in the untagged one.
REVIEW_QUEUE_NAME = "Meridian National: Negative Feedback Review"
REVIEW_QUEUE_DESCRIPTION = (
    "Traces a customer marked thumbs-down (user_feedback = 0), auto-routed here for "
    "human review - the 'notify to review' loop."
)

# LangSmith automation (run rule) that routes any run scored user_feedback = 0
# into the review queue server-side. The app's /concierge-api/feedback route
# writes that key; this rule is the product-level automation on top of it.
FEEDBACK_RULE_NAME = "Negative Feedback"
FEEDBACK_RULE_FILTER = 'and(eq(feedback_key, "user_feedback"), eq(feedback_score, 0))'
