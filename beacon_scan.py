import subprocess
import signal
import sys
import os

# hciconfig
# sudo hciconfig hci1 up

# start scan and dump processes
# TODO: redirect stdout of scan, catch errors of hcitool
scan = subprocess.Popen(['sudo', 'hcitool', 'lescan', '--duplicates'])
dump = subprocess.Popen(['sudo', 'hcidump', '-x', '-R', '-i', 'hci1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
cur_packet = ""
ibeacon_id = "1E 02 01 06 1A FF 4C 00 02 15"

# kill processes on exiting of program
def signal_handler(signal, frame):
    print('You pressed Ctrl+C!')
    os.killpg(scan.pid, signal.SIGTERM)
    os.killpg(dump.pid, signal.SIGTERM)
    sys.exit(0)
signal.signal(signal.SIGINT, signal_handler)

try:
    for line in iter(dump.stdout.readline, b''):
        output_str = line.rstrip()

        # check if new packet as packet is split into multiple lines
        if line[0] is ">":
            print(">>> " + cur_packet)
            # check if all lines are received
            if len(cur_packet) > 120:
                # check for ibeacon advertisement
                # http://www.warski.org/blog/2014/01/how-ibeacons-work/
                index = cur_packet.find(ibeacon_id)
                if index != -1:
                    uuid_start = index + len(ibeacon_id) + 1
                    # 47 is the length of the UUID
                    uuid_end = uuid_start + 47
                    uuid = cur_packet[uuid_start:uuid_end]
                    # last byte of packet contains RSSI information
                    rssi = int(cur_packet[-2:], 16) - 256
                    print("UUID: {}, RSSI: {}".format(uuid, rssi))

            cur_packet = line.strip()
            continue
        else:
            cur_packet += " " + line.strip()
finally:
    os.killpg(scan.pid, signal.SIGTERM)
    os.killpg(dump.pid, signal.SIGTERM)
    print("exiting...")

