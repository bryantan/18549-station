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
        self.settings_dict = {}
        self.uuid_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.settings_last_updated = None

        # kill processes on exiting of program
        def signal_handler(signal, frame):
            print('You pressed Ctrl+C!')
            os.killpg(self.scan.pid, signal.SIGTERM)
            os.killpg(self.dump.pid, signal.SIGTERM)
            sys.exit(0)
        signal.signal(signal.SIGINT, signal_handler)

        # start new threads to receive packets,
        # send packets, and update settings
        rp_thread = threading.Thread(target=self.receive_packets, args=())
        sp_thread = threading.Thread(target=self.send_packets, args=())
        us_thread = threading.Thread(target=self.update_settings, args=())
        rp_thread.start()
        sp_thread.start()
        us_thread.start()

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
                            self.uuid_lock.acquire()
                            self.uuid_dict[uuid] = rssi
                            self.uuid_lock.release()
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
        # TODO: move to constant
        threading.Timer(5.0, self.send_packets).start()
        try:
            # dump received packets and send them to webserver
            json_dict = json.dumps(self.uuid_dict)
            self.uuid_lock.acquire()
            # data = {'data': json.dumps(self.uuid_dict)}
            data = {'data': json_dict}
            # clear dict after sending to ensure fresh values
            self.uuid_dict.clear()
            self.uuid_lock.release()
            print "POST data: " + str(data)
            requests.post('http://128.237.204.130:8000/newData', data=data)
        except Exception as e:
            print "Unable to post data: " + str(e)

    def update_settings(self):
        # TODO: move to constant
        threading.Timer(60.0, self.update_settings).start()
        try:
            # no need to update settings if the file has not changed
            statbuf = os.stat('settings.conf')
            if statbuf.st_mtime == self.settings_last_updated:
                return

            # read settings from file and update the dict
            f = open('settings.conf', 'r', os.O_NONBLOCK)
            settings = json.loads(f.read())
            self.settings_lock.acquire()
            self.settings_dict = settings
            self.settings_lock.release()
            print "New settings: " + str(self.settings_dict)
            self.settings_last_updated = statbuf.st_mtime
        except Exception as e:
            print "Unable to load settings: " + str(e)

    def get_setting(self, key):
        # safely get setting with locking
        self.settings_lock.acquire()
        setting = self.settings_dict.get(key)
        self.settings_lock.release()
        if setting is None:
            print "Setting {} does not exist!".format(key)
            return None
        else:
            return setting


BeaconScanner()
