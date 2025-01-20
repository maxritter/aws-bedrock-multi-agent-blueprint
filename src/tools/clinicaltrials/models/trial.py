from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class LocationContact(BaseModel):
    name: Optional[str] = Field(None, description="Contact name and degree")
    role: Optional[str] = Field(None, description="Contact role/investigator type")
    phone: Optional[str] = Field(None, description="Contact phone number")
    phone_ext: Optional[str] = Field(None, description="Phone extension")
    email: Optional[str] = Field(None, description="Contact email")


class Location(BaseModel):
    facility: Optional[str] = Field(None, description="Facility name")
    status: Optional[str] = Field(None, description="Individual site recruitment status")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State/Province")
    zip: Optional[str] = Field(None, description="ZIP/Postal code")
    country: Optional[str] = Field(None, description="Country")
    country_code: Optional[str] = Field(None, description="ISO country code")
    contacts: Optional[List[LocationContact]] = Field(None, description="Facility contacts")
    geo_point: Optional[Dict[str, float]] = Field(None, description="Geographical coordinates")


class ClinicalTrial(BaseModel):
    nct_id: str = Field(..., description="The NCT ID / ClinicalTrials.gov identifier of the trial")
    phase: Optional[str] = Field(None, description="Phase of the clinical trial")
    org_study_id: Optional[str] = Field(None, description="Organization's unique study identifier")
    status: Optional[str] = Field(None, description="Current recruitment status")
    condition: Optional[str] = Field(None, description="Conditions under study")
    completion_date: Optional[str] = Field(None, description="Primary completion date")
    enrollment_count: Optional[int] = Field(None, description="Number of participants enrolled")
    study_type: Optional[str] = Field(None, description="Type of study")
    arm: Optional[str] = Field(None, description="Study arm label")
    drug: Optional[str] = Field(None, description="Intervention name")
    study_population: Optional[str] = Field(None, description="Description of study population")
    sponsor: Optional[str] = Field(None, description="Lead sponsor name")
    collaborator: Optional[str] = Field(None, description="Study collaborators")
    start_date: Optional[str] = Field(None, description="Study start date")
    primary_measure: Optional[str] = Field(None, description="Primary outcome measure")
    purpose: Optional[str] = Field(None, description="Primary purpose of the study")
    brief_title: Optional[str] = Field(None, description="Brief title of the study")


class MinimalClinicalTrial(BaseModel):
    nct_id: str = Field(..., description="The NCT ID / ClinicalTrials.gov identifier of the trial")
    brief_title: str = Field(..., description="Brief title of the study")


class NearbyTrial(BaseModel):
    nct_id: str = Field(..., description="The NCT ID of the trial")
    distance_km: float = Field(..., description="Distance to the closest location in kilometers")
    closest_location: Location = Field(..., description="Details of the closest location")
