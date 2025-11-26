"""
File Classifier Router - Pre-routes uploaded files before LLM processing.
Classifies uploads as BOOKING_ORDER or ARTWORK with high confidence routing.
"""

import config
from workflows.bo_parser import BookingOrderParser
from integrations.slack.bo_messaging import get_user_real_name

logger = config.logger


async def classify_and_route_file(
    files: list,
    user_input: str,
    user_id: str,
    channel: str,
    status_ts: str,
    slack_event: dict,
    image_files: list,
    document_files: list,
    download_func,
    handle_bo_parse_func
) -> bool:
    """
    Classify a single uploaded file and route if high confidence.

    Returns:
        True if file was routed and handled (caller should return early)
        False if LLM should continue processing
    """
    # PRE-ROUTING CLASSIFIER: Classify and route files before LLM
    if len(files) == 1:
        logger.info(f"[PRE-ROUTER] Single file upload detected, running classification...")

        try:
            file_info = files[0]

            # Download file
            tmp_file = await download_func(file_info)
            logger.info(f"[PRE-ROUTER] Downloaded: {tmp_file}")

            # Classify using existing classifier (converts to PDF, sends to OpenAI, returns classification)
            user_name = await get_user_real_name(user_id) if user_id else None
            parser = BookingOrderParser(company="backlite")  # Company will be determined by classifier
            classification = await parser.classify_document(tmp_file, user_message=user_input, user_id=user_name)

            logger.info(f"[PRE-ROUTER] Classification: {classification}")

            # Route based on HIGH confidence only
            if classification.get("classification") == "BOOKING_ORDER" and classification.get("confidence") == "high":
                company = classification.get("company", "backlite")  # Get company from classifier
                logger.info(f"[PRE-ROUTER] HIGH CONFIDENCE BOOKING ORDER ({company}) - routing directly")

                # Route to booking order parser
                await handle_bo_parse_func(
                    company=company,
                    slack_event=slack_event,
                    channel=channel,
                    status_ts=status_ts,
                    user_notes="",
                    user_id=user_id,
                    user_message=user_input
                )
                return True  # Exit early - don't call LLM

            elif classification.get("classification") == "ARTWORK" and classification.get("confidence") == "high":
                logger.info(f"[PRE-ROUTER] HIGH CONFIDENCE ARTWORK - letting LLM handle mockup")
                tmp_file.unlink(missing_ok=True)
                # Clear document_files and set as image for LLM to handle as mockup
                document_files.clear()
                if not image_files:  # If not already marked as image
                    image_files.append(file_info.get("name", "artwork"))
                # Fall through to LLM for mockup generation
                return False

            else:
                logger.info(f"[PRE-ROUTER] Low/medium confidence - letting LLM decide")
                tmp_file.unlink(missing_ok=True)
                # Fall through to LLM
                return False

        except Exception as e:
            logger.error(f"[PRE-ROUTER] Classification/routing failed: {e}", exc_info=True)
            # Fall through to LLM on error
            return False

    return False
