from flask import Flask, jsonify
import json
#from beacon_scanner import BeaconScanner

app = Flask(__name__)


@app.route('/get_beacons')
def get_beacons():
    f = open('dict', 'r')
    return jsonify(json.loads(f.read()))
    #Zreturn "Hello World!"

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')
