* dnstap *
dnstap is a program used to tap into a local named
daemon, capture dns requests, and then forward those
requests to any interested party.

It works by using a feature of named which can be
enabled during compile time which forwards requests
to a preset unix socket.  This daemon then listens
on that socket, captures forwarded requests, breaks
their format down, and forwards them.

An example run can be found by running bin/dnstap_client.py
