"""Trader-specific parser profiles."""

from src.signal_chain_lab.parser.trader_profiles.base import ParserContext, TraderParseResult, TraderProfileParser
from src.signal_chain_lab.parser.trader_profiles.registry import canonicalize_trader_code, get_profile_parser
from src.signal_chain_lab.parser.trader_profiles.trader_a import TraderAProfileParser
from src.signal_chain_lab.parser.trader_profiles.trader_b import TraderBProfileParser
from src.signal_chain_lab.parser.trader_profiles.trader_c import TraderCProfileParser
from src.signal_chain_lab.parser.trader_profiles.trader_d import TraderDProfileParser
from src.signal_chain_lab.parser.trader_profiles.trader_3 import Trader3ProfileParser

__all__ = [
    "ParserContext",
    "TraderParseResult",
    "TraderProfileParser",
    "TraderAProfileParser",
    "TraderBProfileParser",
    "TraderCProfileParser",
    "TraderDProfileParser",
    "Trader3ProfileParser",
    "canonicalize_trader_code",
    "get_profile_parser",
]
