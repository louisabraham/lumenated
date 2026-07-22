"""lumenated — control the Lumenate Nova light mask + a light/sound session generator.

Independent, unofficial reverse-engineering for interoperability with a device you own.
See the project README for the protocol, safety notes, and license.
"""
from .core import (
    Nova, NovaInfo, Segment,
    strobe_frame, strobe_frame_lr, decode_strobe_frame,
    parse_session, sample_session, session_duration,
    OFFLINE_RELAXED, OFFLINE_EXPLORE, OFFLINE_SLEEP, OFFLINE_NOT_SET,
    REMOTE_EVENTS,
)

__version__ = "0.1.0"

__all__ = [
    "Nova", "NovaInfo", "Segment",
    "strobe_frame", "strobe_frame_lr", "decode_strobe_frame",
    "parse_session", "sample_session", "session_duration",
    "OFFLINE_RELAXED", "OFFLINE_EXPLORE", "OFFLINE_SLEEP", "OFFLINE_NOT_SET",
    "REMOTE_EVENTS", "__version__",
]
