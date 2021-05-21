
'''
    связывание 
    UmDom Devices (tpdo index subindex bit) <-> Domoticz Devices (TYPE SUBTYPE ID)
'''
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

    def __init__(self, Unit, tpdo, map, devid, rpdo) -> None:
        self.Unit = Unit
        self.map = map
        self.tpdo = tpdo
        self.rpdo = rpdo
        self.ID = 0
        self.devid = devid
        self.Name = f'{tpdo.cob_id:X}.{map.name}' 
        self.nValue = 0
        self.sValue = ''        

    def update(self, pdo, map) -> bool:
        self.sValue = f'{map.phys}'
        return True

    def notify(self, Command, Level, Hue):
        pass

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

    def __init__(self, Unit, tpdo, map, id, rpdo) -> None:
        super().__init__(Unit, tpdo, map, id, rpdo)
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

    def update(self, pdo, map) -> bool:
        old = self.nValue
        if map.phys & self.mask:
            self.nValue = 1
        else:
            self.nValue = 0
        return old != self.nValue

    def notify(self, Command, Level, Hue):
        if self.isInput:
            return
        self.rpdo['GPIO pack.SetReset'].phys = self.cmds[Command]
        self.rpdo.transmit()

class Shell(BaseUD):
        INDEXES=(0x1026,)
        SUBTYPE=19

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

    def __init__(self, Unit, tpdo, map, id, rpdo) -> None:
        super().__init__(Unit, tpdo, map, id, rpdo)
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

    def update(self, pdo, map) -> bool:
        sub = map.subindex
        if sub == 3:
            self.temp = map.phys
            self.filldata = self.filldata | 1
        elif sub == 4:
            self.humid = map.phys
            self.filldata = self.filldata | 2
        elif sub == 5:     
            self.bar = map.phys
            self.filldata = self.filldata | 4

        if self.filldata == self._CHMASK:
            self._update_svalue()
            self.filldata = 0
            return True
        else:
            return False    

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

UDs = [ADC50Hz, IOUD, BME280, AM2320, BH1750]
# UDs = [IOUD]
