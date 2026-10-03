import re
from typing import List, Dict, Optional, Tuple
from src.models import ProcessStatus, RecipientSearchResult
from src.validation import normalize_phone


def analyze_search_results(
    results: List[RecipientSearchResult],
    target_phone: str,
    target_patient_name: Optional[str] = None,
) -> Tuple[bool, ProcessStatus, Optional[RecipientSearchResult], str]:
    """
    Analyzes search results returned by Weave against the target phone and patient name.

    Returns:
        (is_verified: bool, status: ProcessStatus, selected_result: Optional[RecipientSearchResult], reason: str)
    """
    if not results:
        return False, ProcessStatus.NO_RECIPIENT_FOUND, None, "No search results returned from Weave."

    norm_target_phone = normalize_phone(target_phone)
    target_digits = re.sub(r"\D", "", norm_target_phone)

    # Filter matching items based on phone number substring/exact digit match
    matched_by_phone: List[RecipientSearchResult] = []
    for item in results:
        item_digits = re.sub(r"\D", "", item.phone or item.raw_text)
        if target_digits and target_digits in item_digits:
            matched_by_phone.append(item)

    if not matched_by_phone:
        # Check if text contains phone
        for item in results:
            if target_digits[-7:] in item.raw_text:
                matched_by_phone.append(item)

    if not matched_by_phone:
        return (
            False,
            ProcessStatus.NO_RECIPIENT_FOUND,
            None,
            f"No matching contact found for target phone ending in {target_digits[-4:]}.",
        )

    if len(matched_by_phone) > 1:
        # Check if they belong to the same person or different people
        unique_names = set(res.name for res in matched_by_phone if res.name)

        if len(unique_names) > 1:
            if target_patient_name:
                norm_target_name = target_patient_name.lower().strip()
                filtered_by_name = [
                    res for res in matched_by_phone
                    if res.name and (norm_target_name in res.name.lower() or res.name.lower() in norm_target_name)
                ]
                if len(filtered_by_name) == 1:
                    return True, ProcessStatus.READY_TO_SEND, filtered_by_name[0], "Recipient verified by phone and name."
                elif len(filtered_by_name) == 0:
                    return (
                        False,
                        ProcessStatus.RECIPIENT_MISMATCH,
                        None,
                        f"Multiple phone matches found, but none matched patient name '{target_patient_name}'.",
                    )
            
            return (
                False,
                ProcessStatus.AMBIGUOUS_RECIPIENT,
                None,
                f"Ambiguous results: {len(matched_by_phone)} matching contacts found for phone.",
            )

        # All results belong to the same named recipient (e.g. Home vs Mobile)
        # Select Mobile if available, otherwise first
        mobile_match = next((res for res in matched_by_phone if res.role_label and "mobile" in res.role_label.lower()), matched_by_phone[0])
        return True, ProcessStatus.READY_TO_SEND, mobile_match, "Single recipient identified with multiple lines."

    # Exactly 1 phone match found
    single_match = matched_by_phone[0]

    # Verify patient name if provided and available
    if target_patient_name and single_match.name:
        norm_target = target_patient_name.lower().strip()
        norm_matched = single_match.name.lower().strip()
        
        # Check name token overlap
        target_tokens = set(norm_target.split())
        matched_tokens = set(norm_matched.split())

        if not (target_tokens & matched_tokens):
            return (
                False,
                ProcessStatus.RECIPIENT_MISMATCH,
                single_match,
                f"Phone matched but name mismatch: expected '{target_patient_name}', got '{single_match.name}'.",
            )

    return True, ProcessStatus.READY_TO_SEND, single_match, "Recipient confidently verified."
