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
    market_type: Optional[str] = None
    main_market_pick: Optional[str] = None
    double_chance_pick: Optional[str] = None
    prob_home: float
    prob_draw: float
    prob_away: float
    prob_1x: Optional[float] = None
    prob_x2: Optional[float] = None
    prob_12: Optional[float] = None
    main_market_probability: Optional[float] = None
    double_chance_probability: Optional[float] = None
    best_probability: Optional[float] = None
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
    bookmaker: Optional[str] = None
    opening_market_odds: Optional[float] = None
    latest_market_odds: Optional[float] = None
    edge: Optional[float] = None
    has_value_bet: bool = False
    fair_odds: Optional[float] = None
    movement: Optional[float] = None
    movement_direction: Optional[str] = None

    class Config:
        from_attributes = True


class PredictionListResponse(BaseModel):
    items: List[PredictionOut]
    total: int
