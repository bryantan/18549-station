import subprocess
import threading
import requests
# import getpass
import signal
import json
import sys
import os

import constants


class BeaconScanner:
    def __init__(self):
        # start scan and dump processes, don't show scan output
        # TODO: catch errors of hcitool
        # password = getpass.getpass()
        scanargs = "sudo hcitool lescan --duplicates".split(" ")
        dumpargs = "sudo hcidump -x -R -i {}".format(constants.HCI_DEVICE) \
                                             .split(" ")
        devnull = open(os.devnull, 'wb')
        self.scan = subprocess.Popen(scanargs,
                                     stdin=subprocess.PIPE,
                                     stdout=devnull)
        # self.scan.stdin.write(password + '\n')
        # self.scan.stdin.close()
        self.dump = subprocess.Popen(dumpargs,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        self.uuid_dict = {}
        self.sent_uuids = {}
        self.last_rssi_values = {}
        self.settings_dict = {}
        self.uuid_lock = threading.Lock()
        self.settings_lock = threading.Lock()
        self.settings_last_updated = None
        self.id = None
        self.ip_address = None

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
        # us_thread = threading.Thread(target=self.update_settings, args=())
        # ui_thread = threading.Thread(target=self.update_id, args=())
        rp_thread.start()
        # sp_thread.start()
        sh_thread.start()
        # us_thread.start()
        # ui_thread.start()
        os.system('./blink_led.sh&')

    def get_dict(self):
        return self.uuid_dict

    def get_average_rssi(self, uuid, new_rssi):
        if uuid not in self.last_rssi_values:
            # Initialize RSSI values
            self.last_rssi_values[uuid] = [-70]*constants.NUMBER_LAST_RSSI_VALUES
        # Update array of last rssi values
        self.last_rssi_values[uuid] = [new_rssi] + self.last_rssi_values[uuid][:-1]
        # Get the average of the last rssi values
        average_rssi = reduce(lambda x,y: x+y, self.last_rssi_values[uuid]) / float(len(self.last_rssi_values[uuid]))
        return int(average_rssi)

    def receive_packets(self):
        cur_packet = ""
        try:
            for line in iter(self.dump.stdout.readline, b''):
                # check if new packet as packet is split into multiple lines
                if line[0] is ">":
                    # print(">>> " + cur_packet)
                    # check for ibeacon advertisement
                    # http://www.warski.org/blog/2014/01/how-ibeacons-work/
                    index = cur_packet.find(constants.IBEACON_ID)
                    if index != -1:
                        uuid_start = index + len(constants.IBEACON_ID) + 1
                        # 47 is the length of the UUID
                        uuid_end = uuid_start + 47
                        # check if complete uuid is received
                        if uuid_end < len(cur_packet):
                            uuid = cur_packet[uuid_start:uuid_end].replace(" ", "")
                            # last byte of packet contains RSSI information
                            rssi = int(cur_packet[-2:], 16) - 256
                            average_rssi = self.get_average_rssi(uuid, rssi)
                            # send if beyond threshold
                            if uuid in self.uuid_dict and \
                               average_rssi <= self.uuid_dict[uuid] * (1 - constants.RSSI_THRESHOLD) and \
                               average_rssi >= self.uuid_dict[uuid] * (1 + constants.RSSI_THRESHOLD):
                                pass
                            else:
                                # lock for thread safety
                                self.uuid_lock.acquire()
                                self.uuid_dict[uuid] = average_rssi
                                self.uuid_lock.release()
                                # send post request to server
                                json_dict = json.dumps({uuid: average_rssi})
                                self.read_latest_id()
                                self.read_latest_ip_address()
                                if self.id is None:
                                    data = {'data': json_dict}
                                else:
                                    data = {'id': self.id,
                                            'data': json_dict}
                                if self.ip_address:
                                    print "POST data to " + self.ip_address + " : " + str(data)
                                    try:
                                        requests.post(self.ip_address + '/newData', data=data)
                                    except Exception as e:
                                        print "Unable to post data: " + str(e)
                            # print("UUID: {}, RSSI: {}".format(uuid, rssi))

                    # look for IP broadcast packet
                    index = cur_packet.find("FF {} {}".format(constants.COMPANY_ID,
                                                              constants.IP_PACKET_ID))
                    if cur_packet.find("02 01 06") != -1 and index != -1:
                        # 15 is the length of FF + company ID + ip packet ID
                        ip_start = index + 15
                        ip_end = cur_packet.find(constants.IP_PACKET_END)
                        server_ip_str = cur_packet[ip_start:ip_end].strip()
                        # convert into string representing IP
                        server_ip = server_ip_str.replace(" ", "") \
                                                 .decode("hex")
                        server_ip = "http://{}:3000".format(server_ip)
                        self.save_latest_ip_address(server_ip)

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
        threading.Timer(constants.SEND_PACKET_PERIOD, self.send_packets).start()
        try:
            # remove values in the dict that are within the threshold range
            new_sent = self.uuid_dict.copy()
            self.uuid_lock.acquire()
            for uuid, rssi in self.uuid_dict.iteritems():
                print str(uuid) + str(rssi)
                if uuid in self.sent_uuids and \
                   rssi <= self.sent_uuids[uuid] + constants.RSSI_THRESHOLD and \
                   rssi >= self.sent_uuids[uuid] - constants.RSSI_THRESHOLD:
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
            self.read_latest_id()
            self.read_latest_ip_address()
            if self.ip_address:
                if self.id is None:
                    data = {'data': json_dict}
                else:
                    data = {'id': self.id, 'data': json_dict}
                print "POST data: " + str(data)
                requests.post(self.ip_address + '/newData', data=data)
        except Exception as e:
            print "Unable to post data: " + str(e)

    def send_heartbeat(self):
        threading.Timer(constants.SEND_HEARTBEAT_PERIOD, self.send_heartbeat).start()
        try:
            self.read_latest_id()
            self.read_latest_ip_address()
            if self.ip_address:
                if self.id is not None:
                    data = {'id': self.id}
                    requests.post(self.ip_address + '/sendHeartbeat', data=data)
        except Exception as e:
            print "Unable to post data: " + str(e)

    def update_settings(self):
        threading.Timer(constants.UPDATE_SETTINGS_PERIOD, self.update_settings).start()
        try:
            # no need to update settings if the file has not changed
            statbuf = os.stat(constants.SETTINGS_FILENAME)
            if statbuf.st_mtime == self.settings_last_updated:
                return

            # read settings from file and update the dict
            f = open(constants.SETTINGS_FILENAME, 'r', os.O_NONBLOCK)
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

        threading.Timer(constants.UPDATE_SETTINGS_PERIOD, self.update_id).start()
        try:
            # read ID from file and update the ID variable
            f = open(constants.ID_FILENAME, 'r', os.O_NONBLOCK)
            id_object = json.loads(f.read())
            self.id = id_object['id']
            print "New ID: " + str(self.id)
        except Exception as e:
            print "Unable to load ID: " + str(e)

    def read_latest_id(self):
        try:
            # read ID from file and update the ID variable
            f = open(constants.ID_FILENAME, 'r', os.O_NONBLOCK)
            id_object = json.loads(f.read())
            self.id = id_object['id']
            f.close()
        except Exception as e:
            print "Unable to load ID: " + str(e)

    def read_latest_ip_address(self):
        try:
            # read ID from file and update the ID variable
            f = open(constants.IP_ADDRESS_FILENAME, 'r', os.O_NONBLOCK)
            self.ip_address = f.read()
            f.close()
        except Exception as e:
            if not self.ip_address:
                print "No IP Address: " + str(e)

    def save_latest_ip_address(self, server_ip):
        print "Received IP Address from BLE: " + server_ip
        if server_ip != self.ip_address:
            self.ip_address = server_ip
            f = open(constants.IP_ADDRESS_FILENAME, 'w', os.O_NONBLOCK)
            f.write(server_ip)
            f.flush()
            f.close()

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
