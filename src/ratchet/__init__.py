"""Ratchet — earned autonomy.

Autonomy as a measured, per-operation, revocable budget rather than a design-time
binary. Operation classes start in shadow, climb on verified evidence, and fall on
one disagreement.

    from ratchet.authority import AuthorityLedger, Authority
    from ratchet.effects import Effect, EffectLog, Actuator
    from ratchet.world import VirtualWorld, verify
    from ratchet.graph import build_app, Deps

`authority`, `effects` and `world` import nothing from ADK or Google Cloud — the
logic that decides whether the agent may act is provable in a plain unit test.
`graph` is the only module that touches the framework.
"""

from .authority import Authority, AuthorityLedger, OperationRecord
from .effects import Actuator, Effect, EffectLog, fingerprint
from .world import Delta, FaultProfile, Verdict, VirtualWorld, verify

__all__ = [
    "Actuator",
    "Authority",
    "AuthorityLedger",
    "Delta",
    "Effect",
    "EffectLog",
    "FaultProfile",
    "OperationRecord",
    "Verdict",
    "VirtualWorld",
    "fingerprint",
    "verify",
]
__version__ = "0.1.0"
