import subprocess
import threading
import requests
# import getpass
import signal
import json
import sys
import os

from constants import *


class BeaconScanner:
    def __init__(self):
        # start scan and dump processes, don't show scan output
        # TODO: catch errors of hcitool
        # password = getpass.getpass()
        scanargs = "sudo hcitool lescan --duplicates".split(" ")
        dumpargs = "sudo hcidump -x -R -i {}".format(HCI_DEVICE).split(" ")
        devnull = open(os.devnull, 'wb')
        self.scan = subprocess.Popen(scanargs, stdin=subprocess.PIPE, stdout=devnull)
        # self.scan.stdin.write(password + '\n')
        # self.scan.stdin.close()
        self.dump = subprocess.Popen(dumpargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.uuid_dict = {}
        self.sent_uuids = {}
        self.settings_dict = {}
        self.uuid_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.settings_last_updated = None
        self.id = None

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
        # sp_thread = threading.Thread(target=self.send_packets, args=())
        sh_thread = threading.Thread(target=self.send_heartbeat, args=())
        us_thread = threading.Thread(target=self.update_settings, args=())
        ui_thread = threading.Thread(target=self.update_id, args=())
        rp_thread.start()
        # sp_thread.start()
        sh_thread.start()
        us_thread.start()
        ui_thread.start()

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
                    index = cur_packet.find(IBEACON_ID)
                    if index != -1:
                        uuid_start = index + len(IBEACON_ID) + 1
                        # 47 is the length of the UUID
                        uuid_end = uuid_start + 47
                        # check if complete uuid is received
                        if uuid_end < len(cur_packet):
                            uuid = cur_packet[uuid_start:uuid_end].replace(" ", "")
                            # last byte of packet contains RSSI information
                            rssi = int(cur_packet[-2:], 16) - 256
                            # send if beyond threshold
                            if uuid in self.uuid_dict and \
                               rssi <= self.uuid_dict[uuid] + RSSI_THRESHOLD and \
                               rssi >= self.uuid_dict[uuid] - RSSI_THRESHOLD:
                                pass
                            else:
                                try:
                                    # lock for thread safety
                                    self.uuid_lock.acquire()
                                    self.uuid_dict[uuid] = rssi
                                    self.uuid_lock.release()
                                    # send post request to server
                                    json_dict = json.dumps({uuid: rssi})
                                    if self.id is None:
                                        data = {'data': json_dict}
                                    else:
                                        data = {'id': self.id,
                                                'data': json_dict}
                                    print "POST data: " + str(data)
                                    requests.post(WEBSERVER_IP + '/newData', data=data)
                                except Exception as e:
                                    print "Unable to post data: " + str(e)
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
        threading.Timer(SEND_PACKET_PERIOD, self.send_packets).start()
        try:
            # remove values in the dict that are within the threshold range
            new_sent = self.uuid_dict.copy()
            self.uuid_lock.acquire()
            for uuid, rssi in self.uuid_dict.iteritems():
                print str(uuid) + str(rssi)
                if uuid in self.sent_uuids and \
                   rssi <= self.sent_uuids[uuid] + RSSI_THRESHOLD and \
                   rssi >= self.sent_uuids[uuid] - RSSI_THRESHOLD:
                    new_sent.pop(uuid, None)
            # clear dict after sending to ensure fresh values
            self.uuid_dict.clear()
            self.uuid_lock.release()
            # do not send if there are no updates
            if len(new_sent) == 0:
                return
            # dump received packets and send them to webserver
            json_dict = json.dumps(new_sent)
            # update sent uuids
            self.sent_uuids = new_sent
            if self.id is None:
                data = {'data': json_dict}
            else:
                data = {'id': self.id, 'data': json_dict}
            print "POST data: " + str(data)
            requests.post(WEBSERVER_IP + '/newData', data=data)
        except Exception as e:
            print "Unable to post data: " + str(e)

    def send_heartbeat(self):
        threading.Timer(SEND_HEARTBEAT_PERIOD, self.send_heartbeat).start()
        try:
            if self.id is not None:
                data = {'id': self.id}
                requests.post(WEBSERVER_IP + '/sendHeartbeat', data=data)
        except Exception as e:
            print "Unable to post data: " + str(e)

    def update_settings(self):
        threading.Timer(UPDATE_SETTINGS_PERIOD, self.update_settings).start()
        try:
            # no need to update settings if the file has not changed
            statbuf = os.stat(SETTINGS_FILENAME)
            if statbuf.st_mtime == self.settings_last_updated:
                return

            # read settings from file and update the dict
            f = open(SETTINGS_FILENAME, 'r', os.O_NONBLOCK)
            settings = json.loads(f.read())
            self.settings_lock.acquire()
            self.settings_dict = settings
            self.settings_lock.release()
            print "New settings: " + str(self.settings_dict)
            self.settings_last_updated = statbuf.st_mtime
        except Exception as e:
            print "Unable to load settings: " + str(e)

    def update_id(self):
        # no need to update settings if there is an ID
        # if self.id is not None:
        #      return

        threading.Timer(UPDATE_SETTINGS_PERIOD, self.update_id).start()
        try:
            # read ID from file and update the ID variable
            f = open(ID_FILENAME, 'r', os.O_NONBLOCK)
            id_object = json.loads(f.read())
            self.id = id_object['id']
            print "New ID: " + str(self.id)
        except Exception as e:
            print "Unable to load ID: " + str(e)

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
