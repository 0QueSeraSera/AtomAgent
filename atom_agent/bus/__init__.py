"""Message bus module for decoupled channel-agent communication."""

from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
