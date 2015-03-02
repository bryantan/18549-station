import subprocess
import signal
import sys
import os

# hciconfig
# sudo hciconfig hci1 up

# start scan and dump processes, don't show scan output
# TODO: catch errors of hcitool
scanargs = "sudo hcitool lescan --duplicates".split(" ")
dumpargs = "sudo hcidump -x -R -i hci1".split(" ")
devnull = open(os.devnull, 'wb')
scan = subprocess.Popen(scanargs, stdout=devnull)
dump = subprocess.Popen(dumpargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
cur_packet = ""
ibeacon_id = "1E 02 01 06 1A FF 4C 00 02 15"
uuid_dict = dict()


# kill processes on exiting of program
def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    os.killpg(scan.pid, signal.SIGTERM)
    os.killpg(dump.pid, signal.SIGTERM)
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

try:
    for line in iter(dump.stdout.readline, b''):
        # check if new packet as packet is split into multiple lines
        if line[0] is ">":
            print(">>> " + cur_packet)
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
                    uuid_dict[uuid] = rssi
                    print("UUID: {}, RSSI: {}".format(uuid, rssi))

            # start tracking of new packet
            cur_packet = line.strip()
            continue
        else:
            cur_packet += " " + line.strip()
finally:
    os.killpg(scan.pid, signal.SIGTERM)
    os.killpg(dump.pid, signal.SIGTERM)
    print("exiting...")
