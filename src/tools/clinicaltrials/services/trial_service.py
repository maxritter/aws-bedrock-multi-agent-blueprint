import re
from typing import Dict, List, Optional

from aws_lambda_powertools import Logger
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from models.trial import ClinicalTrial, Location, MinimalClinicalTrial, NearbyTrial
from utils.helpers import (
    calculate_closest_location,
    fetch,
    geocode_address,
    get_collaborators,
    get_first_item,
    get_nested_value,
    process_locations,
    truncate_response,
)

logger = Logger()

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
MAX_TRIALS = 100


def search_trials(
    lead_sponsor_name: Optional[str] = None,
    disease_area: Optional[str] = None,
    overall_status: Optional[str] = None,
    location_country: Optional[str] = None,
) -> List[MinimalClinicalTrial]:
    fields = [
        "protocolSection.identificationModule.nctId",
        "protocolSection.identificationModule.briefTitle",
    ]
    params = {"format": "json", "fields": ",".join(fields), "pageSize": MAX_TRIALS, "countTotal": "true"}

    logger.info("Constructing query...")
    if disease_area:
        params["query.cond"] = disease_area.replace(" ", "+")
    if lead_sponsor_name:
        params["query.lead"] = lead_sponsor_name.replace(" ", "+")
    if location_country:
        params["query.locn"] = location_country.replace(" ", "+")
    if overall_status:
        params["filter.overallStatus"] = overall_status.upper()
    logger.info(f"Full parameters: {params}")

    all_studies = []
    next_page_token = None
    while True:
        try:
            if next_page_token:
                params["pageToken"] = next_page_token

            response_data = fetch(url=BASE_URL, params=params)

            if not response_data or not isinstance(response_data, dict):
                logger.error(f"Invalid response data")
                break

            studies = response_data.get("studies", [])
            if not studies:
                logger.info("No more studies found")
                break

            all_studies.extend(studies)
            logger.info(f"Retrieved {len(studies)} studies. Total so far: {len(all_studies)}")
            next_page_token = response_data.get("nextPageToken")
            if not next_page_token or len(all_studies) >= MAX_TRIALS:
                break

        except Exception as e:
            logger.error(f"Error processing page: {str(e)}")
            break

    trials_list = []
    for study in all_studies:
        try:
            trial_info = MinimalClinicalTrial(
                nct_id=get_nested_value(study, ["protocolSection", "identificationModule", "nctId"]),
                brief_title=get_nested_value(study, ["protocolSection", "identificationModule", "briefTitle"]),
            )
            trials_list.append(trial_info)

        except Exception as e:
            logger.error(f"Error processing study: {str(e)}")
            continue

    logger.info(f"Total studies returned: {len(trials_list)}")
    return trials_list


def get_trial_details(nct_id: str) -> ClinicalTrial:
    fields = [
        "protocolSection.identificationModule.nctId",
        "protocolSection.identificationModule.orgStudyIdInfo",
        "protocolSection.identificationModule.briefTitle",
        "protocolSection.conditionsModule.conditions",
        "protocolSection.designModule.phases",
        "protocolSection.statusModule.overallStatus",
        "protocolSection.statusModule.primaryCompletionDateStruct",
        "protocolSection.designModule.enrollmentInfo",
        "protocolSection.designModule.studyType",
        "protocolSection.eligibilityModule.studyPopulation",
        "protocolSection.designModule.designInfo",
        "protocolSection.armsInterventionsModule.armGroups",
        "protocolSection.sponsorCollaboratorsModule.leadSponsor",
        "protocolSection.armsInterventionsModule.interventions",
        "protocolSection.outcomesModule.primaryOutcomes",
        "protocolSection.statusModule.startDateStruct",
    ]
    params = {"format": "json", "fields": ",".join(fields), "query.id": nct_id}

    logger.info(f"Fetching details for NCT ID: {nct_id}")
    response_data = fetch(url=BASE_URL, params=params)

    if not response_data or not isinstance(response_data, dict):
        logger.error(f"Invalid response data")
        raise NotFoundError(f"Trial with NCT ID {nct_id} not found")

    studies = response_data.get("studies", [])
    if not studies:
        logger.error(f"No trial found with NCT ID: {nct_id}")
        raise NotFoundError(f"Trial with NCT ID {nct_id} not found")

    study = studies[0]
    try:
        return ClinicalTrial(
            nct_id=get_nested_value(study, ["protocolSection", "identificationModule", "nctId"]),
            phase=get_first_item(study, ["protocolSection", "designModule", "phases"]),
            org_study_id=get_nested_value(study, ["protocolSection", "identificationModule", "orgStudyIdInfo", "id"]),
            status=get_nested_value(study, ["protocolSection", "statusModule", "overallStatus"]),
            condition="|".join(get_nested_value(study, ["protocolSection", "conditionsModule", "conditions"], [])),
            completion_date=get_nested_value(
                study, ["protocolSection", "statusModule", "primaryCompletionDateStruct", "date"]
            ),
            enrollment_count=get_nested_value(study, ["protocolSection", "designModule", "enrollmentInfo", "count"]),
            study_type=get_nested_value(study, ["protocolSection", "designModule", "studyType"]),
            arm=get_first_item(study, ["protocolSection", "armsInterventionsModule", "armGroups"], "label"),
            drug=get_first_item(study, ["protocolSection", "armsInterventionsModule", "interventions"], "name"),
            study_population=get_nested_value(study, ["protocolSection", "eligibilityModule", "studyPopulation"]),
            sponsor=get_nested_value(study, ["protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "name"]),
            collaborator=get_collaborators(study),
            start_date=get_nested_value(study, ["protocolSection", "statusModule", "startDateStruct", "date"]),
            primary_measure=get_first_item(study, ["protocolSection", "outcomesModule", "primaryOutcomes"], "measure"),
            purpose=get_nested_value(study, ["protocolSection", "designModule", "designInfo", "primaryPurpose"]),
            brief_title=get_nested_value(study, ["protocolSection", "identificationModule", "briefTitle"]),
        )

    except Exception as e:
        logger.error(f"Error processing study: {str(e)}")
        raise NotFoundError("Error processing trial details")


def get_trial_locations(nct_id: str) -> List[Location]:
    """Fetch just the locations for a trial."""
    fields = [
        "protocolSection.contactsLocationsModule.locations",
    ]
    params = {"format": "json", "fields": ",".join(fields), "query.id": nct_id}

    response_data = fetch(url=BASE_URL, params=params)
    if not response_data or not isinstance(response_data, dict):
        return []

    studies = response_data.get("studies", [])
    if not studies:
        return []

    study = studies[0]
    return process_locations(study)


def get_closest_trials(
    nct_ids: List[str],
    city: Optional[str] = None,
    state: Optional[str] = None,
    zip_code: Optional[str] = None,
    country: Optional[str] = None,
    max_distance: Optional[float] = 500,
) -> List[NearbyTrial]:
    """Find trials closest to the user's location."""
    user_lat, user_lon = geocode_address(city, state, zip_code, country)
    nearby_trials = []

    for nct_id in nct_ids:
        try:
            nct_id = nct_id.strip()
            locations = get_trial_locations(nct_id)

            if not locations:
                continue

            result = calculate_closest_location(locations, user_lat, user_lon, max_distance)
            if result:
                distance, closest_loc = result
                nearby_trials.append(
                    NearbyTrial(
                        nct_id=nct_id,
                        distance_km=distance,
                        closest_location=closest_loc,
                    )
                )

        except Exception as e:
            logger.error(f"Error processing trial {nct_id}: {str(e)}")
            continue

    return sorted(nearby_trials, key=lambda x: x.distance_km)


def get_inclusion_criteria(nct_id: str) -> Optional[str]:
    params = {"format": "json", "fields": "protocolSection.eligibilityModule.eligibilityCriteria", "query.id": nct_id}
    try:
        response = fetch(url=BASE_URL, params=params)
        if not response or not response.get("studies"):
            logger.error(f"No data found for Trial NCT ID: {nct_id}")
            return None

        eligibility_criteria = response["studies"][0]["protocolSection"]["eligibilityModule"]["eligibilityCriteria"]
        inclusion_criteria = re.split(r"\b(?:Exclusion\s+Criteria:?)\b", eligibility_criteria, flags=re.IGNORECASE)[
            0
        ].strip()
        inclusions = re.split(r"\r?\n+", inclusion_criteria)

        cleaned_inclusions = []
        for inclusion in inclusions:
            inclusion = inclusion.strip()
            if (
                inclusion
                and not re.search(r"^\s*inclusion\s+criteria:?\s*$", inclusion, flags=re.IGNORECASE)
                and not re.search(r"^\s*[-•*]\s*$", inclusion)
            ):
                inclusion = re.sub(r"^\s*[-•*]\s*", "", inclusion)
                if inclusion:
                    cleaned_inclusions.append(inclusion)

        formatted_inclusions = []
        for i, inclusion in enumerate(cleaned_inclusions, 1):
            if not inclusion.endswith("."):
                inclusion = inclusion + "."
            formatted_inclusions.append(f"{i}. {inclusion}")

        return truncate_response("\n".join(formatted_inclusions))

    except Exception as e:
        logger.error(f"Error processing inclusion criteria for Trial NCT ID {nct_id}: {str(e)}")
        return None


def get_exclusion_criteria(nct_id: str) -> Optional[str]:
    params = {"format": "json", "fields": "protocolSection.eligibilityModule.eligibilityCriteria", "query.id": nct_id}

    try:
        response = fetch(url=BASE_URL, params=params)
        if not response or not response.get("studies"):
            logger.error(f"No data found for Trial NCT ID: {nct_id}")
            return None

        eligibility_criteria = response["studies"][0]["protocolSection"]["eligibilityModule"]["eligibilityCriteria"]
        try:
            exclusion_criteria = re.split(r"\b(?:Exclusion\s+Criteria:?)\b", eligibility_criteria, flags=re.IGNORECASE)[
                1
            ].strip()
        except IndexError:
            try:
                exclusion_criteria = re.split(r"(?i)(?:^|\n)\s*exclusion criteria\s*[:|-]?", eligibility_criteria)[
                    1
                ].strip()
            except IndexError:
                logger.error(f"Could not find exclusion criteria section for Trial NCT ID: {nct_id}")
                return None

        exclusions = re.split(r"\r?\n+", exclusion_criteria)

        cleaned_exclusions = []
        for exclusion in exclusions:
            exclusion = exclusion.strip()
            if exclusion and not re.search(r"^\s*$", exclusion) and not re.search(r"^\s*[-•*]\s*$", exclusion):
                exclusion = re.sub(r"^\s*[-•*]\s*", "", exclusion)
                if exclusion:
                    cleaned_exclusions.append(exclusion)

        formatted_exclusions = []
        for i, exclusion in enumerate(cleaned_exclusions, 1):
            if not exclusion.endswith("."):
                exclusion = exclusion + "."
            formatted_exclusions.append(f"{i}. {exclusion}")

        return truncate_response("\n".join(formatted_exclusions))

    except Exception as e:
        logger.error(f"Error processing exclusion criteria for Trial NCT ID {nct_id}: {str(e)}")
        return None
