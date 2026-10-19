"""Compose existing read-only analysis with pure rules, without another repository."""
from app.market.contracts import AnalysisRequest
from app.market.service import MarketAnalysisService
from app.market.signal_contracts import MarketSignalsResponse, SignalParameters
from app.market.signals import evaluate_signals


class MarketSignalService:
    def analyze(self, request: AnalysisRequest, parameters: SignalParameters) -> MarketSignalsResponse:
        analysis = MarketAnalysisService().analyze(request)
        return evaluate_signals(analysis, parameters)
