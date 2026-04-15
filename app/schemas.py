from pydantic import BaseModel, EmailStr
from typing import Optional, List


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    is_active: bool

    class Config:
        from_attributes = True


class DashboardSummaryResponse(BaseModel):
    total_predictions: int
    resolved_predictions: int
    hits: int
    misses: int
    accuracy: float
    pending_predictions: int
    high_confidence_predictions: int
    value_bets: int


class PredictionOut(BaseModel):
    id: int
    fixture_id: str
    league_name: str
    home_team: str
    away_team: str
    match_date: str
    match_time: str
    pick: str
    prob_home: float
    prob_draw: float
    prob_away: float
    confidence: str
    model_source: Optional[str]
    status: str
    result: Optional[str]
    home_score: Optional[int]
    away_score: Optional[int]

    class Config:
        from_attributes = True


class PredictionListResponse(BaseModel):
    items: List[PredictionOut]
    total: int