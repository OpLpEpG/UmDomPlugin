# UmDomPlugin
Domotocz UmDom Python Plugin

## Orange PI PC connect mcp2515

POWER:
https://vimtut0r.com/2017/01/17/can-bus-with-raspberry-pi-howtoquickstart-mcp2515-kernel-4-4-x/

1. PC0 SPI0_MOSI
2. PC1 SPI0_MISO
3. PC2 SPI0_CLK
4. PC3 SPI0_CS
5. PA2 INT

![alt text](https://i.pinimg.com/originals/65/05/e0/6505e0d0c55c4101b5214d43de5e62af.png)

## Orange PI PC setup
 file spi-mcp251x.dts, armbian overlay source for compile and setup
```
/dts-v1/;
/plugin/;

/ {
	compatible = "allwinner,sun4i-a10", "allwinner,sun7i-a20", "allwinner,sun8i-h3", "allwinner,sun50i-a64", "allwinner,sun50i-h5";

	fragment@0 {
		target-path = "/clocks";
		__overlay__ {
			#address-cells = <1>;
			#size-cells = <1>;
			can0_osc_fixed: can0_osc_fixed {
				compatible = "fixed-clock";
				#clock-cells = <0>;
				clock-frequency  = <8000000>;
			};
		};
	};

	fragment@1 {
		target = <&pio>;
		__overlay__ {
			can0_pin_irq: can0_pin_irq {
				pins = "PA2";
				function = "irq";
				bias-pull-up;
			};
		};
	};

	fragment@2 {
		target = <&spi0>;
		__overlay__ {
			#address-cells = <1>;
			#size-cells = <0>;
			status = "okay";
			mcp2515 {
				reg = <0>;
				compatible = "microchip,mcp2515";
				pinctrl-names = "default";
				pinctrl-0 = <&can0_pin_irq>;
				spi-max-frequency = <10000000>;
				interrupt-parent = <&pio>;
				interrupts = <0 2 8>; /* PA7 IRQ_TYPE_LEVEL_LOW */
				clocks = <&can0_osc_fixed>;
				status = "okay";
			};
		};
	};
};

```
file /boot/armbianEnv.txt
```
verbosity=2
bootlogo=false
console=serial
disp_mode=1920x1080p60
overlay_prefix=sun8i-h3
rootdev=UUID=aff6ba2e-d36d-49aa-ad59-aa8599c3de78
rootfstype=ext4
user_overlays=spi-mcp251x
overlays=uart3
usbstoragequirks=0x2537:0x1066:u,0x2537:0x1068:u

```
file /etc/network/interfaces

```
...........................
auto can0
iface can0 can static
    bitrate 125000
..........................
```