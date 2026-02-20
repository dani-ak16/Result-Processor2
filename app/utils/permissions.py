def can_edit_results(role):
    return role in ["admin", "subject_teacher"]


def can_approve_results(role):
    return role == "admin"


def can_manage_students(role):
    return role in ["admin", "class_teacher"]
