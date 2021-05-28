"""
<plugin key="CanOpenPlug" name="Canopen Umdom" author="oplpepg" version="1.0.0">
    <description>
        <h2>Umdom Domoticz Plugin</h2><br/>
        доманняя автоматизация по сети CAN,
        протоколу Canopen    
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>controllers:    Bluepill STM32F103 128KB </li>
            <li>can:            TJA1050</li>
            <li>OS:             Zephyr OS</li>
            <li>OS subsistem:   shell, canopennode</li>
        </ul>
        <h3>Sensors</h3>
        <ul style="list-style-type:square">
            <li>BME280</li>
            <li>AM2320</li>
            <li>BH1750</li>
            <li>ACS712 measure 50Hz current</li>
            <li>GPIOs</li>
        </ul>
        <h3>Configuration</h3>
        Canopen node scanner find node then find eds file
        <ul style="list-style-type:square">
            <li>node EDS file : bp%d.eds %d-canopen address</li>
            <li>default EDS file : bp.eds</li>
        </ul>
        Domoticz devices generated only then find mapped dictionary items in TPDO
    </description>
    <params>
        <param field="Mode1" label="CAN Interface" default="can0" width="150px" required="true"/>
        <param field="Mode2" label="Path to EDS files" default="/home/oleg" width="150px" required="true"/>
    </params>
</plugin>
"""

# import debugpy
## Allow other computers to attach to debugpy at this IP address and port.
# debugpy.listen(('0.0.0.0', 5678))

## Pause the program until a remote debugger is attached
# debugpy.wait_for_client()

import Domoticz
from canopenUD import UmdomNet
from domoticzUD import GetUDclass

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
                        if u:
                            if u in self.udDevices:
                                ud = self.udDevices[u]
                            else: 
                                ud = CreateUD()    
                        else:
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
                self.udDevices[Unit].notify(Command, Level, Hue)
            except BaseException as e:
                Domoticz.Error(f'{e}')
        else:
            Domoticz.Error('Softeare ERROR!!! Unit {Unit} not found in udDevices')

    

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onCommand(Unit, Command, Level, Hue):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Hue)


def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
    return

