
from app.ai.schemas import Issue


# Steps where the customer needs to provide information first.
CUSTOMER_STEPS = {
    "ask-details",
    "ask-photos",
    "ask-dimensions",
}


def resolve_issue(issue: Issue) -> str:
    """
    Decide the next step for a reported furniture problem.
    Python makes the final decision, not the AI model.
    """

    step = next_step(issue)

    if step not in CUSTOMER_STEPS | {"escalate"}:
        if not issue.order_number:
            return "ask-details"

    return step


def next_step(issue: Issue) -> str:
    # Office furniture
    if issue.product == "office-furniture":

        if issue.problem == "missing-part":
            return "escalate"

        if issue.problem == "damaged-product":
            return "ask-photos"

        if issue.problem == "wrong-product":
            return "escalate"

        if issue.problem == "defective-product":
            return "escalate"

        if issue.problem == "assembly-issue":
            return "ask-photos"

    # Workstations and cubicles
    if issue.product == "workstation":

        if issue.problem == "layout-enquiry":
            return "ask-dimensions"

        if issue.problem == "missing-part":
            return "escalate"

        if issue.problem == "damaged-panel":
            return "ask-photos"

        if issue.problem == "installation-issue":
            return "escalate"

        if issue.problem == "partition-issue":
            return "escalate"

    # Office cabins and interiors
    if issue.product == "office-cabin":

        if issue.problem == "design-enquiry":
            return "ask-dimensions"

        if issue.problem == "installation-issue":
            return "escalate"

        if issue.problem == "structural-damage":
            return "ask-photos"

        if issue.problem == "modification-request":
            return "escalate"

    # Chairs and seating
    if issue.product == "chair":

        if issue.problem == "missing-part":
            return "escalate"

        if issue.problem == "damaged-product":
            return "ask-photos"

        if issue.problem == "mechanism-not-working":
            return "ask-photos"

        if issue.problem == "defective-product":
            return "escalate"

    # Orders and installation
    if issue.product == "order":

        if issue.problem == "delivery-issue":
            return "escalate"

        if issue.problem == "installation-delay":
            return "escalate"

        if issue.problem == "order-status":
            return "escalate"

        if issue.problem == "cancellation":
            return "escalate"

    # Unknown issues always go to a colleague.
    return "escalate"
