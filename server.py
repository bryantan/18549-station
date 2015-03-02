from flask import Flask, jsonify
import ast
#from beacon_scanner import BeaconScanner

app = Flask(__name__)


@app.route('/get_beacons')
def get_beacons():
    f = open('dict', 'r')
    uuid_dict = ast.literal_eval(f.read())
    return jsonify(**uuid_dict)
    #Zreturn "Hello World!"

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')
