"""Template context: expose permissions and navbar data."""
from .models import CATEGORY_CHOICES

def stage_permissions(request):
    if request.user.is_authenticated:
        choices = dict(CATEGORY_CHOICES)
        allowed = request.user.allowed_categories()
        return {
            'user_can_edit': request.user.can_edit(),
            'user_can_request_issue': request.user.can_request_issue(),
            'user_can_approve_issue_requests': request.user.can_approve_issue_requests(),
            'user_can_issue_items': request.user.can_issue_items(),
            'user_can_manage_users': request.user.can_manage_users(),
            'user_is_stage1': request.user.is_stage1(),
            'user_allowed_categories': allowed,
            'category_display': choices,
            'navbar_categories': [{'slug': c, 'name': choices.get(c, c)} for c in allowed],
        }
    return {
        'user_can_edit': False,
        'user_can_request_issue': False,
        'user_can_approve_issue_requests': False,
        'user_can_issue_items': False,
        'user_can_manage_users': False,
        'user_is_stage1': False,
        'user_allowed_categories': [],
        'category_display': dict(CATEGORY_CHOICES),
        'navbar_categories': [{'slug': c[0], 'name': c[1]} for c in CATEGORY_CHOICES],
    }
