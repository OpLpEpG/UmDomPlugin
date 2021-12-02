
'''
    связывание 
    UmDom Devices (tpdo index subindex bit) <-> Domoticz Devices (TYPE SUBTYPE ID)
'''
import json
import time
from threading import Timer


def GetUDclass(pdo, map):
    for cls in UDs:
        if cls.IsClass(pdo, map):
            return cls
    raise ValueError(f'Device type not found  pdo: {pdo.cob_id:X} index: {map.index:X}:{map.subindex:X}, name: {map.name}')

class BaseUD:
    INDEXES=(0x6400, 0x6401)
    MULTIPLE_DEVS=False
    TYPE=243
    SUBTYPE=0

    @classmethod 
    def IsClass(cls, pdo, map) -> bool:
        return map.index in cls.INDEXES

    @classmethod 
    def GetRootID(cls, pdo, map) -> str:
        return f'{pdo.cob_id:X}.{map.index:X}'

    @classmethod 
    def GenerateDeviceIDs(cls, node, pdo, map) -> list:
        return [cls.GetRootID(pdo, map)]

    def __init__(self, Unit, tpdo, map, devid, rpdo, log) -> None:
        self.Unit = Unit
        self.map = map
        self.tpdo = tpdo
        self.rpdo = rpdo
        self.log = log
        self.ID = 0
        self.devid = devid
        self.Name = f'{tpdo.cob_id:X}.{map.name}' 
        self.nValue = 0
        self.sValue = ''      
    # update UD device from canopen device    
                        # def event (Unit nValue sValue):
                        #     Devices[ud.Unit].Update (nValue=ud.nValue,sValue=ud.sValue)
    def update(self, pdo, map, event):
        sv = f'{map.phys}'
        if sv != self.sValue:
            self.sValue = sv
            event(self.Unit, self.nValue, self.sValue)
    #write to canopen device     
    # return: flag need to update Domoticz device 
    def notify(self, Command, Level, Hue) -> bool:
        return False
    # json api modify Domoticz device
    # return: flag need to update Domoticz device 
    def device_modified(self, nValue, sValue):
        return False


class ADC50Hz(BaseUD):
    INDEXES=(0x6400, 0x6401)
    TYPE = 243   # General
    SUBTYPE = 23 # Ampere (1 Phase)

    @classmethod 
    def GetRootID(cls, pdo, map):
        return f'{pdo.cob_id:X}.{map.index:X}.{map.subindex:X}'

class IOUD(BaseUD):
    INDEXES=(0x2080,)
    MULTIPLE_DEVS=True
    TYPE = 244  # Light/Switch
    SUBTYPE = 62 # Selector Switch
    MASK={}

    @classmethod
    def GenerateDeviceIDs(cls, node, pdo, map) -> list:
        if pdo.cob_id in cls.MASK:
            maski, masko = cls.MASK[pdo.cob_id]
        else:
            maski = (node.sdo[map.index][1]).phys
            masko = (node.sdo[map.index][2]).phys
            cls.MASK[pdo.cob_id] = (maski, masko)

        RootID = cls.GetRootID(pdo, map)
        i = [f'{RootID}-INP-{i}' for i in range(0,16) if maski & (1 << i)]
        o = [f'{RootID}-OUT-{i}' for i in range(0,16) if masko & (1 << i)]
        return i+o

    def __init__(self, Unit, tpdo, map, id, rpdo, log) -> None:
        super().__init__(Unit, tpdo, map, id, rpdo, log)
        self.nValue = -1
        ids = id.split('-')
        # ids[0] = RootID
        # ids[1] = 'INP'/'OUT'
        # ids[2] = cannel 0..15
        self.isInput = ids[1] == 'INP'
        if self.isInput:
            self.ID = 2
        self.ch = int(ids[2])
        self.mask = 1 << self.ch
        self.cmds = {'On':self.mask, 'Off':self.mask << 16}
        self.Name += ('-'+ids[1] + ids[2])

    def update(self, pdo, map, event):
        old = self.nValue
        if map.phys & self.mask:
            self.nValue = 1
        else:
            self.nValue = 0
        if old != self.nValue:
            event(self.Unit, self.nValue, self.sValue)

    def notify(self, Command, Level, Hue):
        if self.isInput:
            return False
        self.rpdo['GPIO pack.SetReset'].phys = self.cmds[Command]
        self.rpdo.transmit()
        return False

class Shell(BaseUD):
    INDEXES=(0x1026,)
    SUBTYPE=19
    STATE_CHAR=0 
    STATE_STR=1
    STATE_LINES=2
    CMD_CLEAR_LINES=3

    def __init__(self, Unit, tpdo, map, id, rpdo, log) -> None:
        super().__init__(Unit, tpdo, map, id, rpdo, log)
        # self.state = self.STATE_STR
        self.lines = []     # STATE_LINES
        self.char = 0      # STATE_CHAR 
        self._lastCodes = [0,0,0];     
        self._last_line= '' # STATE_STR bytearray(b'')
        self._time = time.time()

    def _create_json_svalue(self, cmd, val):
        obj = {'cmd':cmd, 'stat':'data', 'data':val}
        return json.dumps(obj)

    def _parse_json_svalue(self, val):
        cmd = -1
        data = None
        try:
            obj = json.loads(val)
            if 'stat' in obj and obj['stat'] == 'get':
                if 'cmd' in obj:
                    cmd = obj['cmd']
                if 'data' in obj:
                    data = obj['data']    
                    
        except:
            return (-1, None)
        return (cmd, data)

    def _add_last_code(self, c):
        self._lastCodes[0] = self._lastCodes[1]
        self._lastCodes[1] = self._lastCodes[2]    
        self._lastCodes[2] = c
    def _check_esc_end(self):
        return (self._lastCodes[0] == 0x1B) and (self._lastCodes[1] == 0x5B) and (self._lastCodes[2] == 0x6D)             


    # stdOut
    def update(self, pdo, map, event):
        # bad string
        if map.phys == 0:
            self._last_line = ''    
            return

        self._add_last_code(map.phys)
        self.char = chr(map.phys)
        self._last_line += self.char

        def UpdateDev():
            self.sValue = self._last_line
            self._last_line =''
            self.lines.append(self.sValue)
            event(self.Unit, self.nValue, self.sValue)

        t = time.time()
        dt = t - self._time
        self._time = t
        # self.log(dt)
        if (dt < 0.2) and (map.phys != 0x0A) and not self._check_esc_end():
            if hasattr(self, "_timer"):
                self._timer.cancel()
            def cb():
                if self._last_line != '':
                    UpdateDev()
            self._timer = Timer(0.1, cb)
            self._timer.start()
            return
        else:    
            UpdateDev()


    def _send_char(self, ch):
        self.rpdo['OS prompt.StdIn'].phys = ord(ch)
        self.rpdo.transmit()

    # json api modify Domoticz device
    #  /json.htm?type=command&param=udevice&idx=37&nvalue=0&svalue={"cmd":2,"stat":"get"}&parsetrigger=false
    # return: flag need to update Domoticz device 
    # stdIn
    def device_modified(self, nValue, sValue):

        cmd, data = self._parse_json_svalue(sValue)

        if cmd == self.STATE_CHAR:
            self._send_char(data)

        elif cmd == self.STATE_STR:
            for s in list(data):
                self._send_char(s)
                time.sleep(0.02)
                    
        elif cmd == self.CMD_CLEAR_LINES:
            self.lines.clear()
            self._last_line =''
            self.sValue = self._create_json_svalue(self.CMD_CLEAR_LINES, [])
            return True

        elif cmd == self.STATE_LINES:
            self.sValue = self._create_json_svalue(self.STATE_LINES, self.lines)                 
            return True 

        return False    


class BME280(BaseUD):
    #Temperature/humidity/barometer
    #nvalue=0&svalue=TEMP;HUM;HUM_STAT;BAR;BAR_FOR
    # Barometer forecast can be one of:
    # 0 = No info
    # 1 = Sunny
    # 2 = Partly cloudy
    # 3 = Cloudy
    # 4 = Rain
    INDEXES=(0x200C,0x200D,0x200E,0x200F)
    TYPE = 84   # Temp+Hum+Baro
    SUBTYPE = 1 # THB1 - BTHR918, BTHGN129
    _CHMASK = 7

    def __init__(self, Unit, tpdo, map, id, rpdo, log) -> None:
        super().__init__(Unit, tpdo, map, id, rpdo, log)
        self.filldata = 0
        # filldata 001 tmp
        # filldata 010 hum
        # filldata 100 bar
        # filldata 111 all data ready
        self.temp = 0
        self.humid = 0
        self.bar = 0
        
    def _update_svalue(self):
            self.sValue = f'{self.temp};{self.humid};0;{self.bar};0'

    def update(self, pdo, map, event):
        sub = map.subindex
        if sub == 3:
            self.temp = map.phys
            self.filldata |= 1
        elif sub == 4:
            self.humid = map.phys
            self.filldata |= 2
        elif sub == 5:     
            self.bar = map.phys
            self.filldata |= 4

        if self.filldata == self._CHMASK:
            old = self.sValue
            self._update_svalue()
            self.filldata = 0
            if old != self.sValue:
                event(self.Unit, self.nValue, self.sValue)

class AM2320(BME280):    
    #Temp+Hum
    #nvalue=0&svalue=TEMP;HUM;HUM_STAT
    # HUM_STAT can be one of:
    # 0=Normal
    # 1=Comfortable
    # 2=Dry
    # 3=Wet
    INDEXES=(0x200A,0x200B)
    TYPE = 82  #Temp+Hum
    SUBTYPE = 1 #LaCrosse TX3
    _CHMASK = 3

    def _update_svalue(self):
            self.sValue = f'{self.temp};{self.humid};0'

class BH1750(BaseUD):
    #Lux Illumination (sValue: "float")
    INDEXES=(0x2006,0x2007,0x2008,0x2009)
    TYPE = 246  #Lux
    SUBTYPE = 1  #Lux (sValue: "float")

UDs = [ADC50Hz, IOUD, BME280, AM2320, BH1750, Shell]
# UDs = [Shell]
