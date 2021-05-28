import os
import struct
import canopen
from canopen.emcy import EmcyConsumer, EmcyError
from canopen.node import RemoteNode
from threading import Thread, Event

# try:
#     import Domoticz
#     def Log(msg):
#         Domoticz.Log(msg)
#     # Log('=====================Canopen Domoticz========================')    
# except:
#     import logging
#     logging.basicConfig()
#     log = logging.getLogger()
#     log.setLevel(logging.INFO)
#     def Log(msg):
#         log.'info'(msg)

class UmdomNet:

    def __init__(self, channel, eds_path, sendTime_time = 600, sync_time = 10):
        # Log('=====================Canopen Domoticz========================') 
        self.controllers = {}
        self.channel = channel    
        self.tpdo_callback = None
        self.new_node_callback = None
        self.heartbeat_err_node_callback = None
        self.emcy_node_callback = None
        self.except_callback = None
        self.eds_path = eds_path
        self.sendTime_time = sendTime_time
        self.sync_time = sync_time

    def addController(self, id):
        c = ControllerThread(self, id)
        self.controllers[id] = c
        c.start()

    def start(self):        
        self.network = MyNetwork(self)
        self.network.connect(self.channel, bustype='socketcan')
        self.timesendthread = TimeSendThread(self)
        self.timesendthread.start()        
        self.network.scanner.reset()
        self.network.sync.start(self.sync_time)
        return self.network

    def stop(self):
        for n in self.controllers.values():
            n.stop()
        self.timesendthread.stop()        
        self.network.sync.stop()
        self.network.disconnect()
        self.network = None

class MyNetwork(canopen.Network):
    def __init__(self, ud: UmdomNet, bus=None):
        super().__init__(bus=bus)
        self.scanner = MyNodeScanner(ud, network = self)

    def add_node(self, node, object_dictionary=None, upload_eds=False):
        if isinstance(node, int):
            node = MyRemoteNode(node, object_dictionary)
        self[node.id] = node
        return node

class MyNodeScanner(canopen.NodeScanner):    

    def __init__(self, ud: UmdomNet, network = None):
        super().__init__(network = network)
        self.ud = ud

    def on_message_received(self, can_id):
        service = can_id & 0x780
        node_id = can_id & 0x3F
        if node_id not in self.nodes and node_id != 0 and service in self.SERVICES:
            self.nodes.append(node_id)
            self.ud.addController(node_id)

class MyRemoteNode(RemoteNode):
    def __init__(self, node_id, object_dictionary, load_od=False):
        super().__init__(node_id, object_dictionary, load_od=load_od)
        self.emcy = MyEmcyConsumer()

# Error code, error register, CanOpenNode Error status bits, vendor specific data
EMCY_STRUCT = struct.Struct("<HBB4s")

class MyEmcyConsumer(EmcyConsumer):

    def on_emcy(self, can_id, data, timestamp):
        code, register, key, data = EMCY_STRUCT.unpack(data)
        entry = MyEmcyError(code, register, key, data, timestamp)

        with self.emcy_received:
            if code & 0xFF00 == 0:
                # Error reset
                self.active = []
            else:
                self.active.append(entry)
            self.log.append(entry)
            self.emcy_received.notify_all()

        for callback in self.callbacks:
            callback(entry)


class MyEmcyError(EmcyError):

    #CanOpenNode Error status bits descriptions
    CANOPEN_NODE_EMCY={
        0x00 : ('generic', 'info', 'Error Reset or No Error'),
        0x01 : ('communication', 'info', 'CAN bus warning limit reached'),
        0x02 : ('communication', 'info', 'Wrong data length of the received CAN message'),
        0x03 : ('communication', 'info', 'Previous received CAN message wasn`t processed yet'),
        0x04 : ('communication', 'info', 'Wrong data length of received PDO'),
        0x05 : ('communication', 'info', 'Previous received PDO wasn`t processed yet'),
        0x06 : ('communication', 'info', 'CAN receive bus is passive'),
        0x07 : ('communication', 'info', 'CAN transmit bus is passive'),
        0x08 : ('communication', 'info', 'Wrong NMT command received'),
        0x09 : ('communication', 'info', 'TIME message timeout'),
        0x0A : ('communication', 'info', 'Unexpected TIME data length'),
        0x12 : ('communication', 'critical', 'CAN transmit bus is off'),
        0x13 : ('communication', 'critical', 'CAN module receive buffer has overflowed'),
        0x14 : ('communication', 'critical', 'CAN transmit buffer has overflowed'),
        0x15 : ('communication', 'critical', 'TPDO is outside SYNC window'),
        0x18 : ('communication', 'critical', 'SYNC message timeout'),
        0x19 : ('communication', 'critical', 'Unexpected SYNC data length'),
        0x1A : ('communication', 'critical', 'Error with PDO mapping'),
        0x1B : ('communication', 'critical', 'Heartbeat consumer timeout'),
        0x1C : ('communication', 'critical', 'Heartbeat consumer detected remote node reset'),
        0x20 : ('generic', 'info', 'Emergency buffer is full, Emergency message wasn`t sent'),
        0x22 : ('generic', 'info', 'Microcontroller has just started'),
        0x28 : ('generic', 'critical', 'Wrong parameters to CO_errorReport() function'),
        0x29 : ('generic', 'critical', 'Timer task has overflowed'),
        0x2A : ('generic', 'critical', 'Unable to allocate memory for objects'),
        0x2B : ('generic', 'critical', 'Generic error, test usage'),
        0x2C : ('generic', 'critical', 'Software error'),
        0x2D : ('generic', 'critical', 'Object dictionary does not match the software'),
        0x2E : ('generic', 'critical', 'Error in calculation of device parameters'),
        0x2F : ('generic', 'critical', 'Error with access to non volatile device memory'),
    }
    #Standard error codes according to CiA DS-301 and DS-401.
    DESCRIPTIONS=[
        (0x8110, 0xFFFF, 'CAN Overrun (Objects lost)'),
        (0x8120, 0xFFFF, 'CAN in Error Passive Mode'),
        (0x8130, 0xFFFF, 'Life Guard Error or Heartbeat Error'),
        (0x8140, 0xFFFF, 'recovered from bus off'),
        (0x8150, 0xFFFF, 'CAN-ID collision'),
        (0x8210, 0xFFFF, 'PDO not processed due to length error'),
        (0x8220, 0xFFFF, 'PDO length exceeded'),
        (0x8230, 0xFFFF, 'DAM MPDO not processed, destination object not available'),
        (0x8240, 0xFFFF, 'Unexpected SYNC data length'),
        (0x8250, 0xFFFF, 'RPDO timeout'),
        (0x8260, 0xFFFF, 'Unexpected TIME data length'),
        (0x2310, 0xFFFF, 'DS401, Current at outputs too high (overload)'),
        (0x2320, 0xFFFF, 'DS401, Short circuit at outputs'),
        (0x2330, 0xFFFF, 'DS401, Load dump at outputs'),
        (0x3110, 0xFFFF, 'DS401, Input voltage too high'),
        (0x3120, 0xFFFF, 'DS401, Input voltage too low'),
        (0x3210, 0xFFFF, 'DS401, Internal voltage too high'),
        (0x3220, 0xFFFF, 'DS401, Internal voltage too low'),
        (0x3310, 0xFFFF, 'DS401, Output voltage too high'),
        (0x3320, 0xFFFF, 'DS401, Output voltage too low'),
        (0x0000, 0xFF00, 'error Reset or No Error'),
        (0x1000, 0xFF00, 'Generic Error'),
        (0x2000, 0xFF00, 'Current'),
        (0x2100, 0xFF00, 'Current, device input side'),
        (0x2200, 0xFF00, 'Current inside the device'),
        (0x2300, 0xFF00, 'Current, device output side'),
        (0x3000, 0xFF00, 'Voltage'),
        (0x3100, 0xFF00, 'Mains Voltage'),
        (0x3200, 0xFF00, 'Voltage inside the device'),
        (0x3300, 0xFF00, 'Output Voltage'),
        (0x4000, 0xFF00, 'Temperature'),
        (0x4100, 0xFF00, 'Ambient Temperature'),
        (0x4200, 0xFF00, 'Device Temperature'),
        (0x5000, 0xFF00, 'Device Hardware'),
        (0x6000, 0xFF00, 'Device Software'),
        (0x6100, 0xFF00, 'Internal Software'),
        (0x6200, 0xFF00, 'User Software'),
        (0x6300, 0xFF00, 'Data Set'),
        (0x7000, 0xFF00, 'Additional Modules'),
        (0x8000, 0xFF00, 'Monitoring'),
        (0x8100, 0xFF00, 'Communication'),
        (0x8200, 0xFF00, 'Protocol Error'),
        (0x9000, 0xFF00, 'External Error'),
        (0xF000, 0xFF00, 'Additional Functions'),
        (0xFF00, 0xFF00, 'Device specific'),
    ]
    def __init__(self, code, register, key, data, timestamp):
        super().__init__(code, register, data, timestamp)
        self.key = key

    def get_canopennode_desc(self):
        if self.key in self.CANOPEN_NODE_EMCY:
            return self.CANOPEN_NODE_EMCY[self.key]
        return ('','','')
    

class TimeSendThread(Thread): 

    def __init__(self, ud: UmdomNet):
        Thread.__init__(self)
        self.ud = ud
        self.event = Event()

    def stop(self):
        self.event.set()
        self.join(1)            

    def run(self):
        while not self.event.wait(self.ud.sendTime_time):
            try:
                self.ud.network.time.transmit()
            except BaseException as e:                
                if self.ud.except_callback:
                    self.ud.except_callback('timer', None, e)

class ControllerThread(Thread):

    def __init__(self, ud: UmdomNet, id, heartbeat_interval=10):
        Thread.__init__(self)
        self.ud = ud
        self.id = id
        self.name = f'node{id}'
        self.heartbeat_interval = heartbeat_interval
        self.terminated = False

    def _get_esd_file(self):
        pf = self.ud.eds_path
        eds = os.path.join(pf, 'bp%d.eds' % self.id) 
        if not os.path.isfile(eds):
            eds = os.path.join(pf, 'bp.eds')
            if not os.path.isfile(eds):
                raise FileNotFoundError(f'Node: {self.id} File {eds} is requested but doesn’t exist')
        return eds


    def on_emcy(self, entry):
        if self.ud.emcy_node_callback:
            self.ud.emcy_node_callback(self.node, entry)

    def run(self):
        try:
            ud = self.ud
            node = ud.network.add_node(self.id, self._get_esd_file())  
            self.node = node  
            node.tpdo.read()
            node.rpdo.read()
            if ud.emcy_node_callback:
                node.emcy.add_callback(self.on_emcy)
            if ud.new_node_callback:
                ud.new_node_callback(node)
            if ud.tpdo_callback:
                for t in node.tpdo.values():
                    t.add_callback(ud.tpdo_callback)
        except BaseException as e:
            if ud.except_callback:
                ud.except_callback(self.id, node, e)
            return
        errCnt = 0    
        while not self.terminated:
            try:
                state = node.nmt.wait_for_heartbeat(timeout = self.heartbeat_interval)
                if state != 'OPERATIONAL':
                    node.nmt.state = 'OPERATIONAL'
                    errCnt += 1
                    if errCnt > 99:
                        ec = errCnt
                        errCnt = 0
                        raise ConnectionError(f'Can`t set nmt OPERATIONAL Error Cnt: {ec}')
                else:
                    errCnt = 0                        
            except BaseException as e:
                if ud.heartbeat_err_node_callback and not self.terminated:
                    ud.heartbeat_err_node_callback(node, state, e)                   

    def stop(self):
        self.terminated = True
        if hasattr(self, 'node'):
            with self.node.nmt.state_update:
                self.node.nmt.state_update.notify_all()
        self.join(1)
