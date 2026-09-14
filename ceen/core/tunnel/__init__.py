"""How your traffic actually leaves your computer.

    pool.py      the basket of currently-working servers, plus the
                 "group by country" view for the Connect screen
    rotator.py   the local tunnel on 127.0.0.1 that forwards your
                 traffic through those servers
    probe.py     double-checks which country you are really exiting from
"""
