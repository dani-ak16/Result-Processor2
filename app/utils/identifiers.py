from models.academic import Student
from datetime import datetime


def generate_reg_number(class_name, arm, session, term, index):
    """
    Generate registration number in CLASSARM-SESSION-TERM-SERIAL format.
    Example: JSS1G-2425-1-003
    """
    # Remove spaces from class name (e.g., "JSS 1" → "JSS1")
    class_abbr = class_name.replace(" ", "").upper()

    # Arm abbreviation (e.g., "Gold" → "G")
    arm_abbr = arm[0].upper() if arm else "A"

    # Convert session format "2024/2025" → "2425"
    session_parts = session.split("/")
    if len(session_parts) == 2:
        session_short = session_parts[0][-2:] + session_parts[1][:2]
    else:
        session_short = session.replace("/", "")[:4]

    return f"{class_abbr}{arm_abbr}-{session_short}-{term}-{index:03d}"
