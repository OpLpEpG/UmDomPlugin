import os
import canopen
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
#         log.info(msg)

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

    def start(self):        
        self.network = canopen.Network()
        self.network.scanner = MyNodeScanner(self)
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

class MyNodeScanner(canopen.NodeScanner):    

    def __init__(self, ud: UmdomNet):
        super().__init__(network = ud.network)
        self.ud = ud

    def on_message_received(self, can_id):
        service = can_id & 0x780
        node_id = can_id & 0x3F
        if node_id not in self.nodes and node_id != 0 and service in self.SERVICES:
            self.nodes.append(node_id)
            c = ControllerThread(self.ud, node_id)
            self.ud.controllers[node_id] = c
            c.start()

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

    def on_emcy(self, entry):
        if self.ud.emcy_node_callback:
            self.ud.emcy_node_callback(self.node, entry)

    def run(self):
        try:
            ud = self.ud
            node = None
            eds = ud.eds_path + '/bp%d.eds' % self.id 
            if not os.path.isfile(eds):
                eds = ud.eds_path +'/bp.eds'
                if not os.path.isfile(eds):
                    raise FileNotFoundError(f'Node: {self.id} File {eds} is requested but doesn’t exist')
            node = ud.network.add_node(self.id, eds)  
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
                    if errCnt > 10:
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
