from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(180), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    fixture_id = Column(String(50), unique=True, index=True, nullable=False)

    league_key = Column(String(50), nullable=True)
    league_name = Column(String(120), nullable=False)

    home_team = Column(String(120), nullable=False)
    away_team = Column(String(120), nullable=False)

    match_date = Column(String(20), nullable=False)
    match_time = Column(String(20), nullable=False)

    pick = Column(String(5), nullable=False)

    prob_home = Column(Float, nullable=False)
    prob_draw = Column(Float, nullable=False)
    prob_away = Column(Float, nullable=False)

    confidence = Column(String(20), nullable=False)
    model_source = Column(String(30), nullable=True)

    status = Column(String(20), default="pending", nullable=False)
    result = Column(String(5), nullable=True)

    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)

    features_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    checked_at = Column(DateTime, nullable=True)

    odds = relationship("PredictionOdds", back_populates="prediction", uselist=False)


class PredictionOdds(Base):
    __tablename__ = "prediction_odds"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), unique=True, nullable=False)

    bookmaker = Column(String(120), nullable=True)

    home_odds = Column(Float, nullable=True)
    draw_odds = Column(Float, nullable=True)
    away_odds = Column(Float, nullable=True)

    fair_home_odds = Column(Float, nullable=True)
    fair_draw_odds = Column(Float, nullable=True)
    fair_away_odds = Column(Float, nullable=True)

    opening_market_odds = Column(Float, nullable=True)
    latest_market_odds = Column(Float, nullable=True)

    edge = Column(Float, nullable=True)
    has_value_bet = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    prediction = relationship("Prediction", back_populates="odds")