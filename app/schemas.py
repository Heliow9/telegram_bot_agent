from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


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
    live_predictions: int = 0
    high_confidence_predictions: int
    value_bets: int

    today_resolved_predictions: int = 0
    today_hits: int = 0
    today_misses: int = 0
    today_accuracy: float = 0.0
    today_live_predictions: int = 0

    profit: float = 0.0
    stake: float = 0.0
    roi: float = 0.0
    roi_items: int = 0

    today_profit: float = 0.0
    today_stake: float = 0.0
    today_roi: float = 0.0
    today_roi_items: int = 0


class PredictionOut(BaseModel):
    id: int
    fixture_id: str
    league_key: Optional[str] = None
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
    model_source: Optional[str] = None
    status: str
    result: Optional[str] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    features_json: Optional[str] = None

    created_at: Optional[datetime] = None
    checked_at: Optional[datetime] = None

    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    result_source: Optional[str] = None
    last_status_text: Optional[str] = None
    is_live: bool = False

    class Config:
        from_attributes = True


class PredictionListResponse(BaseModel):
    items: List[PredictionOut]
    total: int