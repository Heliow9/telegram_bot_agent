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
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class RuntimeConfigState(Base):
    __tablename__ = "runtime_config_state"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String(80), unique=True, index=True, nullable=False)
    config_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    fixture_id = Column(String(50), unique=True, index=True, nullable=False)

    league_key = Column(String(50), nullable=True)
    league_name = Column(String(120), nullable=False, index=True)

    home_team = Column(String(120), nullable=False)
    away_team = Column(String(120), nullable=False)

    match_date = Column(String(20), nullable=False)
    match_time = Column(String(20), nullable=False)

    # pick final enviado pelo sistema
    # exemplos: "1", "X", "2", "1X", "X2", "12"
    pick = Column(String(10), nullable=False)

    # mercado escolhido pelo sistema
    # exemplos: "1x2" | "double_chance"
    market_type = Column(String(30), nullable=True, index=True)

    # pick principal do mercado 1x2
    # exemplos: "1" | "X" | "2"
    main_market_pick = Column(String(5), nullable=True)

    # melhor pick de dupla hipótese
    # exemplos: "1X" | "X2" | "12"
    double_chance_pick = Column(String(5), nullable=True)

    # probabilidades do mercado 1x2
    prob_home = Column(Float, nullable=False, default=0.0)
    prob_draw = Column(Float, nullable=False, default=0.0)
    prob_away = Column(Float, nullable=False, default=0.0)

    # probabilidades do mercado dupla hipótese
    prob_1x = Column(Float, nullable=True)
    prob_x2 = Column(Float, nullable=True)
    prob_12 = Column(Float, nullable=True)

    # probabilidades-resumo para auditoria e comparação final
    main_market_probability = Column(Float, nullable=True)
    double_chance_probability = Column(Float, nullable=True)
    best_probability = Column(Float, nullable=True)

    confidence = Column(String(20), nullable=False)
    model_source = Column(String(30), nullable=True)

    status = Column(String(20), default="pending", nullable=False, index=True)
    result = Column(String(5), nullable=True)

    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)

    features_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    checked_at = Column(DateTime, nullable=True)

    # operação / monitoramento
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    last_checked_at = Column(DateTime, nullable=True)
    result_source = Column(String(50), nullable=True)
    last_status_text = Column(String(100), nullable=True)
    is_live = Column(Boolean, default=False, nullable=False, index=True)

    odds = relationship(
        "PredictionOdds",
        back_populates="prediction",
        uselist=False,
        cascade="all, delete-orphan",
    )


class PredictionOdds(Base):
    __tablename__ = "prediction_odds"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(
        Integer,
        ForeignKey("predictions.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    bookmaker = Column(String(120), nullable=True)

    # odds 1x2
    home_odds = Column(Float, nullable=True)
    draw_odds = Column(Float, nullable=True)
    away_odds = Column(Float, nullable=True)

    # fair odds 1x2
    fair_home_odds = Column(Float, nullable=True)
    fair_draw_odds = Column(Float, nullable=True)
    fair_away_odds = Column(Float, nullable=True)

    # odds dupla hipótese
    odds_1x = Column(Float, nullable=True)
    odds_x2 = Column(Float, nullable=True)
    odds_12 = Column(Float, nullable=True)

    # fair odds dupla hipótese
    fair_odds_1x = Column(Float, nullable=True)
    fair_odds_x2 = Column(Float, nullable=True)
    fair_odds_12 = Column(Float, nullable=True)

    # odds efetivamente usadas para análise do pick final
    opening_market_odds = Column(Float, nullable=True)
    latest_market_odds = Column(Float, nullable=True)

    edge = Column(Float, nullable=True)
    has_value_bet = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    prediction = relationship("Prediction", back_populates="odds")