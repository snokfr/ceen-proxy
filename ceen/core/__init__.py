"""The "brain" of Ceen Proxy — everything that is not the on-screen window.

Sub-packages:
    ceen.core.proxies   one proxy (entry.py), how to talk to proxies
                        (handshakes.py), how to test them (checker.py)
    ceen.core.scanning  testing a whole proxy list in parallel (scanner.py)
    ceen.core.tunnel    your traffic's route out: pool.py (working-server
                        basket), rotator.py (the local tunnel), probe.py
                        ("which country am I really in right now?")

Nothing in here imports tkinter — the brain never touches the window.
"""
