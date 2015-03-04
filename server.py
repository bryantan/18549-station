from flask import Flask, jsonify, request

import json
import os

from constants import SETTINGS_FILENAME
# from beacon_scanner import BeaconScanner

app = Flask(__name__)


# @app.route('/get_beacons')
# def get_beacons():
#     f = open('dict', 'r')
#     return jsonify(json.loads(f.read()))
#     #Zreturn "Hello World!"


@app.route('/set-settings', methods=['POST'])
def set_settings():
    settings = json.loads(request.form['data'])
    # TODO: check settings dict
    f = open(SETTINGS_FILENAME, 'w', os.O_NONBLOCK)
    f.write(json.dumps(settings))
    f.flush()
    return "set"

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')
