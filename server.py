from flask import Flask
#from beacon_scanner import BeaconScanner

app = Flask(__name__)


@app.route('/')
def hello_world():
    f = open('dict', 'r')
    return f.read()
    #Zreturn "Hello World!"

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0')
