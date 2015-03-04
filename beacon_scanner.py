import subprocess
import threading
import requests
# import getpass
import signal
import json
import sys
import os

ibeacon_id = "1E 02 01 06 1A FF 4C 00 02 15"


class BeaconScanner:
    def __init__(self):
        # start scan and dump processes, don't show scan output
        # TODO: catch errors of hcitool
        # password = getpass.getpass()
        scanargs = "sudo hcitool lescan --duplicates".split(" ")
        dumpargs = "sudo hcidump -x -R -i hci0".split(" ")
        devnull = open(os.devnull, 'wb')
        self.scan = subprocess.Popen(scanargs, stdin=subprocess.PIPE, stdout=devnull)
        # self.scan.stdin.write(password + '\n')
        # self.scan.stdin.close()
        self.dump = subprocess.Popen(dumpargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.uuid_dict = {}
        self.lock = threading.Lock()

        # kill processes on exiting of program
        def signal_handler(signal, frame):
            print('You pressed Ctrl+C!')
            os.killpg(self.scan.pid, signal.SIGTERM)
            os.killpg(self.dump.pid, signal.SIGTERM)
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)

        # start new thread to receive packets
        rp_thread = threading.Thread(target=self.receive_packets, args=())
        sp_thread = threading.Thread(target=self.send_packets, args=())
        rp_thread.start()
        sp_thread.start()

    def get_dict(self):
        return self.uuid_dict

    def receive_packets(self):
        cur_packet = ""
        try:
            for line in iter(self.dump.stdout.readline, b''):
                # check if new packet as packet is split into multiple lines
                if line[0] is ">":
                    # print(">>> " + cur_packet)
                    # check for ibeacon advertisement
                    # http://www.warski.org/blog/2014/01/how-ibeacons-work/
                    index = cur_packet.find(ibeacon_id)
                    if index != -1:
                        uuid_start = index + len(ibeacon_id) + 1
                        # 47 is the length of the UUID
                        uuid_end = uuid_start + 47
                        # check if complete uuid is received
                        if uuid_end < len(cur_packet):
                            uuid = cur_packet[uuid_start:uuid_end].replace(" ", "")
                            # last byte of packet contains RSSI information
                            rssi = int(cur_packet[-2:], 16) - 256
                            # lock for thread safety
                            self.lock.acquire()
                            self.uuid_dict[uuid] = rssi
                            self.lock.release()
                            # print("UUID: {}, RSSI: {}".format(uuid, rssi))

                    # start tracking of new packet
                    cur_packet = line.strip()
                    continue
                else:
                    cur_packet += " " + line.strip()
        finally:
            os.killpg(self.scan.pid, signal.SIGTERM)
            os.killpg(self.dump.pid, signal.SIGTERM)
            print("exiting...")

    def send_packets(self):
        threading.Timer(5.0, self.send_packets).start()
        self.lock.acquire()
        # data = {'data': json.dumps(self.uuid_dict)}
        data = {'data': json.dumps(self.uuid_dict)}
        self.uuid_dict.clear()
        self.lock.release()
        print "POST data: " + str(data)
        requests.post('http://128.237.119.104:8000/newData', data=data)

BeaconScanner()
