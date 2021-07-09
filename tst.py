import os
import sys
import can
import canopen
from canopenUD import UmdomNet
from domoticzUD import GetUDclass
import re
import time
from datetime import datetime
from threading import Thread, Event, Condition
# --------------------------------------------------------------------------- #
# configure the client logging
# --------------------------------------------------------------------------- #
import logging
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)


class Domoticz:
    class Device:
        def __init__(self, Name=None, Unit=None, Type=None, Subtype=None, DeviceID=None,Switchtype=None, Options={}) -> None:
            self.Name = Name
            self.Unit = Unit
            self.Type = Type
            self.Subtype = Subtype
            self.DeviceID = DeviceID
            self.Switchtype = Switchtype
            self.Options = Options
            

        def Create(self):
            Devices[self.Unit]=self
            return self

        def Update(self, nValue=0, sValue=''):
            self.nValue = nValue
            self.sValue = sValue
            if self.Subtype == 19:
                print(sValue, end='')
                # Domoticz.Log(f'{sValue}')
            else:    
                pass
                # Domoticz.Log(f'{self.Name}:{sValue}')   
        def Notifier(self, data):
            pass

    def Debugging(dbl):
        pass


Domoticz.Log = log.info
Domoticz.Status = log.info
Domoticz.Debug = log.info
Domoticz.Error = log.error
Domoticz.Notifier = log.info

Devices={}
Parameters={'Mode1':'can0', 'Mode2':'/home/oleg'}

class BasePlugin:
    enabled = False

    def _find_device_unit(self, DeviceID):
        for key, value in Devices.items():
            if DeviceID == value.DeviceID:                 
                return key
        return None

    def _get_empty_unit(self):
        for unit in range(1,256):
            if not (unit in Devices):
                return unit
        raise ValueError('All unit 1-255 exists')

    def _find_rpdo(self, map, rpdos):
        for r in rpdos:
            for m in r:                 
                if m.index == map.index:
                    return r
        return None

    def on_newnode(self, node):
        Domoticz.Log(f' ------------- ADD NODE: {node.id}')        
        rpdos =  [m for m in node.rpdo.values()]   
        tpdos =  [m for m in node.tpdo.values()] 
        # Create domoticz and umdom devices if umdom devices mapped in tpdo
        for t in tpdos:
            for m in t:
                try:
                    if not hasattr(m, 'uds'):
                        m.uds = []                
                    clsUD = GetUDclass(t, m)
                    ids = clsUD.GenerateDeviceIDs(node, t, m)
                    for id in ids:
                        u = self._find_device_unit(id)
                        def CreateUD():
                            r = self._find_rpdo(m, rpdos)
                            d = clsUD(u, t, m, id, r)
                            self.udDevices[u] = d
                            return d
                        if u: # Device exists
                            if u in self.udDevices:
                                ud = self.udDevices[u]
                            else: 
                                ud = CreateUD()    
                        else: # Device need create
                            u = self._get_empty_unit()
                            ud = CreateUD()    
                            Domoticz.Device(Name=ud.Name, Unit=u, Type=ud.TYPE, Subtype=ud.SUBTYPE, DeviceID=id, Switchtype=ud.ID).Create()   
                        m.uds.append(ud)                        
                except BaseException as e:
                    Domoticz.Error(f'{e}')
        # Update data on start
        node.sdo['RTR'].phys = 1

    def on_tpdo(self, maps):
        for m in maps:
            if hasattr(m, 'uds'):
                for ud in m.uds:
                    try:
                        if ud.update(maps, m):
                            Devices[ud.Unit].Update(nValue=ud.nValue,sValue=ud.sValue)
                    except BaseException as e:
                        Domoticz.Error(f'{e}')
                                                                            
    def on_heartbeat_error(self, node, state, e):
        Domoticz.Error(f'node:{node.id} state: {state} {e}')

    def on_emcy(self, node, entry):        
        Domoticz.Error(f'<<<<<<<EMERGENCY>>>>>>: node{node.id} Code:   {entry.code:04X}   Register:  {entry.register:X}  Data:  {entry.data.hex()} Desc: {entry.get_desc()}')
        c1,c2,c3 = entry.get_canopennode_desc()
        Domoticz.Error(f'<<<<<<<EMERGENCY>>>>>>: node{node.id} group: {c1} severity: {c2} desc: {c3}')


    def on_except(self, id, node, e):        
        Domoticz.Error(f'node:{id} error: {e}')

    def onStart(self):
        self.udDevices = {}
        Domoticz.Debugging(1)
        Domoticz.Notifier('UmDom_notify')
        # Domoticz.Trace(True)
        Domoticz.Debug("----------------------onStart called-----------------")
        self.ud = UmdomNet(Parameters['Mode1'], eds_path=Parameters['Mode2'])        
        self.ud.tpdo_callback = self.on_tpdo
        self.ud.new_node_callback = self.on_newnode
        self.ud.heartbeat_err_node_callback = self.on_heartbeat_error
        self.ud.emcy_node_callback = self.on_emcy
        self.ud.except_callback = self.on_except
        self.ud.start()
        DumpConfigToLog()

    def onStop(self):
        Domoticz.Debug("---------------onStop called------------------")
        self.ud.stop()

    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level)+ "hue "+str(Hue))
        if Unit in self.udDevices:
            try:
                d = self.udDevices[Unit]
                if d.notify(Command, Level, Hue):
                    Devices[Unit].Update(nValue=d.nValue,sValue=d.sValue)
            except BaseException as e:
                Domoticz.Error(f'{e}')
        else:
            Domoticz.Error('Softeare ERROR!!! Unit {Unit} not found in udDevices')

    def onNotification(self, Name, Subject, Text, Status, Priority, Sound, ImageFile):
        Domoticz.Status("==========Notification==========: " + Name + "," + Subject + "," + Text + "," + Status + "," + str(
            Priority) + "," + Sound + "," + ImageFile)    


def DumpConfigToLog():
    pass


def tpdo_callback(maps):
    s = f'{datetime.fromtimestamp(maps.timestamp)} cob_id:{maps.cob_id:X} '
    for m in maps:
        s += f'{m.od.name}={m.phys}, '
        # s += f'{m.od.parent.name}.{m.od.name}={m.phys}, '
    print(s)

bp = BasePlugin()
bp.onStart()
time.sleep(5)

while True:
    time.sleep(10)
    for u in bp.udDevices.values():
        if u.INDEXES == (0x1026,):
            u.sValue = ''
            u.notify('i2c scan I2C_1\n',None, None)
            
    # time.sleep(10)
    # bp.udDevices[5].notify('Off',0,0)
    # bp.udDevices[6].notify('Off',0,0)
    # time.sleep(1)
    # bp.udDevices[5].notify('On',0,0)
    # bp.udDevices[6].notify('On',0,0)
    # "192.168.0.106:8080/json.htm?type=devices&plan=21&lastupdate=0&jsoncallback=?"
bp.onStop()