from typing import Annotated, List, Literal, Optional

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import BedrockAgentResolver
from aws_lambda_powertools.event_handler.exceptions import InternalServerError
from aws_lambda_powertools.event_handler.openapi.params import Body, Query
from aws_lambda_powertools.utilities.typing import LambdaContext
from models.trial import ClinicalTrial, MinimalClinicalTrial, NearbyTrial
from services import trial_service

logger = Logger()
tracer = Tracer()
app = BedrockAgentResolver()


@app.get(
    "/search_trials",
    description="Search for clinical trials based on criteria",
    operation_id="searchTrials",
    responses={
        200: {"description": "Successfully retrieved matching clinical trials"},
        500: {"description": "Internal server error occurred while searching trials"},
    },
)
@tracer.capture_method
def search_trials(
    lead_sponsor_name: Annotated[
        Optional[str], Query(description="Name of the lead sponsor organization, f. ex. Boehringer Ingelheim")
    ] = None,
    disease_area: Annotated[
        Optional[str], Query(description="Disease or condition being studied, f. ex. lung cancer")
    ] = None,
    overall_status: Annotated[
        Optional[
            Literal[
                "ACTIVE_NOT_RECRUITING",
                "COMPLETED",
                "ENROLLING_BY_INVITATION",
                "NOT_YET_RECRUITING",
                "RECRUITING",
                "SUSPENDED",
                "TERMINATED",
                "WITHDRAWN",
                "AVAILABLE",
                "NO_LONGER_AVAILABLE",
                "TEMPORARILY_NOT_AVAILABLE",
                "APPROVED_FOR_MARKETING",
                "WITHHELD",
                "UNKNOWN",
            ]
        ],
        Query(description="Current overall status of the study, f. ex. RECRUITING"),
    ] = None,
    location_country: Annotated[
        Optional[str], Query(description="Country where the study is conducted, f. ex. United States")
    ] = None,
) -> Annotated[
    List[MinimalClinicalTrial], Body(description="List of matching clinical trials with minimal information")
]:
    try:
        return trial_service.search_trials(lead_sponsor_name, disease_area, overall_status, location_country)
    except Exception as e:
        logger.exception("Error searching trials")
        raise InternalServerError(str(e))


@app.get(
    "/trial_details",
    description="Get detailed information for a specific clinical trial",
    operation_id="trialDetails",
    responses={
        200: {"description": "Successfully retrieved trial details"},
        404: {"description": "Trial not found"},
        500: {"description": "Internal server error occurred while fetching trial details"},
    },
)
@tracer.capture_method
def trial_details(
    nct_id: Annotated[str, Query(description="The NCT ID of the trial, f. ex. NCT05888888")],
) -> Annotated[ClinicalTrial, Body(description="Detailed information about the clinical trial")]:
    try:
        return trial_service.get_trial_details(nct_id)
    except Exception as e:
        logger.exception("Error getting trial details")
        raise InternalServerError(str(e))


@app.get(
    "/closest_trials",
    description="Find trials closest to the user's location",
    operation_id="closestTrials",
    responses={
        200: {"description": "Successfully found nearby trials"},
        404: {"description": "No trials found within the specified distance"},
        500: {"description": "Internal server error occurred while finding closest trials"},
    },
)
@tracer.capture_method
def closest_trials(
    nct_ids: Annotated[List[str], Query(description="List of NCT IDs")],
    city: Annotated[Optional[str], Query(description="User's city")] = None,
    state: Annotated[Optional[str], Query(description="User's state/province")] = None,
    zip_code: Annotated[Optional[str], Query(description="User's ZIP/postal code")] = None,
    country: Annotated[Optional[str], Query(description="User's country")] = None,
    max_distance: Annotated[Optional[float], Query(description="Maximum distance in kilometers")] = 500,
) -> Annotated[List[NearbyTrial], Body(description="List of trials sorted by distance to the user")]:
    try:
        return trial_service.get_closest_trials(nct_ids, city, state, zip_code, country, max_distance)
    except Exception as e:
        logger.exception("Error finding closest trials")
        raise InternalServerError(str(e))


@app.get(
    "/inclusion_criteria",
    description="Get inclusion criteria for a clinical trial",
    operation_id="getInclusions",
    responses={
        200: {"description": "Successfully retrieved inclusion criteria"},
        404: {"description": "Trial not found or no inclusion criteria available"},
        500: {"description": "Internal server error occurred while fetching inclusion criteria"},
    },
)
@tracer.capture_method
def inclusion_criteria(
    nct_id: Annotated[str, Query(description="The NCT ID of the trial, f. ex. NCT05888888")],
) -> Annotated[str | None, Body(description="Formatted inclusion criteria as a numbered list, or None if not found")]:
    try:
        return trial_service.get_inclusion_criteria(nct_id)
    except Exception as e:
        logger.exception("Error getting inclusion criteria")
        raise InternalServerError(str(e))


@app.get(
    "/exclusion_criteria",
    description="Get exclusion criteria for a clinical trial",
    operation_id="getExclusions",
    responses={
        200: {"description": "Successfully retrieved exclusion criteria"},
        404: {"description": "Trial not found or no exclusion criteria available"},
        500: {"description": "Internal server error occurred while fetching exclusion criteria"},
    },
)
@tracer.capture_method
def exclusion_criteria(
    nct_id: Annotated[str, Query(description="The NCT ID of the trial, f. ex. NCT05888888")],
) -> Annotated[str | None, Body(description="Formatted exclusion criteria as a numbered list, or None if not found")]:
    try:
        return trial_service.get_exclusion_criteria(nct_id)
    except Exception as e:
        logger.exception("Error getting exclusion criteria")
        raise InternalServerError(str(e))


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext):
    try:
        logger.info(f"*** EVENT ***: {event}")
        return app.resolve(event, context)
    except Exception as e:
        logger.exception("Unhandled error in lambda handler")
        raise InternalServerError(str(e))


if __name__ == "__main__":
    print(app.get_openapi_json_schema())
