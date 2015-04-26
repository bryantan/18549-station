from flask import Flask, jsonify, request

import subprocess
import threading
import json
import os

from constants import *
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
    f.close()
    try:
        if 'pollingFreq' in settings:
            contants.SEND_PACKET_PERIOD = int(settings['pollingFreq'])
    except:
        return "error"
    return "set"


@app.route('/set-id', methods=['POST'])
def set_id():
    settings = json.loads(request.form['data'])
    print "Received new ID: " + settings["id"]
    # TODO: check settings dict
    f = open(ID_FILENAME, 'w', os.O_NONBLOCK)
    f.write(json.dumps(settings))
    f.flush()
    f.close()
    return "set"


@app.route('/broadcast-ip', methods=['GET'])
def set_ip():
    server_ip = "http://%s:3000" % request.remote_addr
    f = open(CONSTANTS_FILENAME, 'r+', os.O_NONBLOCK)
    constants_content = f.read()
    constants_content = constants_content.replace(WEBSERVER_IP, server_ip)
    f.seek(0)
    f.write(constants_content)
    f.truncate()
    f.close()
    return "set"


@app.route('/broadcast-uuid', methods=['POST'])
def broadcast_uuid():
    uuid = request.form['uuid']
    # http://stackoverflow.com/questions/16151360/use-bluez-stack-as-a-peripheral-advertiser
    # http://stackoverflow.com/questions/18906988/what-is-the-ibeacon-bluetooth-profile
    # https://github.com/RadiusNetworks/altbeacon-reference/blob/master/altbeacon_transmit
    # TODO: remember to change numbers to hex string
    # TODO: add or remove spaces from uuid
    """
    sudo hciconfig hci0 down
    sudo hciconfig hci0 up
    sudo hciconfig hci0 noleadv
    sudo hciconfig hci0 noscan
    sudo hciconfig hci0 leadv
    sudo hcitool -i hci0 cmd 0x08 0x0008 1e 02 01 1a 1a ff 4c 00 02 15 e2 c5 6d b5 df fb 48 d2 b0 60 d0 f5 a7 10 96 e0 00 00 00 00 c5 00
    sudo hcitool -i hci0 cmd 0x08 0x0008 1e 02 01 06 1a ff 4c 00 02 15 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 33 00 00 00 00 c5 00
    length (1e) is length of packet. there is a trailing 00 at the end
    the 1a doesn't seem to matter even though it's supposed to denote length of some sort...
    """
    formatted_uuid = ""
    for i in xrange(0, len(uuid), 2):
        formatted_uuid += uuid[i:i+2] + " "
    formatted_uuid = formatted_uuid.strip()
    """
    14 comes from: 9 bytes of packet header
                   4 bytes of major/minor
                   1 byte of transmission power
    """
    packet_len = 14 + len(uuid)/2
    packet = "02 01 06 {} FF {} {} {} {}".format(str(hex(packet_len-4))[2:],
                                                 COMPANY_ID,
                                                 BROADCAST_PACKET_ID,
                                                 formatted_uuid,
                                                 "00 00 00 00 c5 00")
    stopargs = "sudo hciconfig {} noleadv".format(HCI_DEVICE).split(" ")
    bcargs = "sudo hcitool -i {} cmd 0x08 0x0008 {} {}".format(HCI_DEVICE,
                                                               str(hex(packet_len))[2:],
                                                               packet) \
                                                       .split(" ")
    startargs = "sudo hciconfig {} leadv".format(HCI_DEVICE).split(" ")
    devnull = open(os.devnull, 'wb')
    subprocess.Popen(stopargs, stdin=subprocess.PIPE, stdout=devnull)
    subprocess.Popen(bcargs, stdin=subprocess.PIPE, stdout=devnull)
    subprocess.Popen(startargs, stdin=subprocess.PIPE, stdout=devnull)

    # limit broadcast packet time
    def stop_broadcast(): subprocess.Popen(stopargs, stdin=subprocess.PIPE, stdout=devnull)
    threading.Timer(BROADCAST_PACKET_PERIOD, stop_broadcast).start()

    return "sent"

if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=8001)
