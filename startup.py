import requests
import json
import os

from constants import *


try:
    resp = requests.post(WEBSERVER_IP + '/register', timeout=5)
    settings = resp.json()
    f = open(SETTINGS_FILENAME, 'w', os.O_NONBLOCK)
    f.write(json.dumps(settings))
    f.flush()
except Exception as e:
    # station is first station, needs to initialize self as webserver
    return
