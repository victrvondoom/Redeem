"""REDEEM Computer Bridge: the companion that lets REDEEM see and operate a computer the user has paired.

It opens no inbound port. It connects out to the REDEEM server over an authenticated WebSocket, executes only the
typed actions in ``protocol.ACTIONS`` and honours a local pause / emergency stop that the server cannot override.
"""
__version__ = "0.1.0"
