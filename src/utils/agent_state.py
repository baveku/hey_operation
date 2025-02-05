import asyncio
from datetime import datetime


class AgentState:
    _instance = None

    def __init__(self):
        if not hasattr(self, '_stop_requested'):
            self._stop_requested = asyncio.Event()
            self.last_valid_state = None  # store the last valid browser state
            self.model_thinking = None
            self.now = int(datetime.now().timestamp())

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentState, cls).__new__(cls)
        return cls._instance

    def request_stop(self):
        self._stop_requested.set()

    def clear_stop(self):
        self._stop_requested.clear()
        self.last_valid_state = None

    def is_stop_requested(self):
        return self._stop_requested.is_set()

    def set_last_valid_state(self, state):
        self.last_valid_state = state

    def set_model_thinking(self, model_thinking):
        self.now = int(datetime.now().timestamp())
        self.model_thinking = model_thinking

    def get_model_thinking(self):
        return self.model_thinking
    
    def will_update_model_thinking(self, old: int):
        return (self.now - old) > 0

    def get_last_valid_state(self):
        return self.last_valid_state