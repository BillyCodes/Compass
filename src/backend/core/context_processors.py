"""Navigation uses the same active business role as the student services."""
from accounts.models import Role
from accounts.permissions import has_role


def navigation(request):
    return {"is_student": has_role(request.user, Role.Name.STUDENT)}
