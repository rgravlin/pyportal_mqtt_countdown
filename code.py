from random import randint
import time
import board                                                            # board pin names (I2C, SPI, UART)
import busio                                                            # serial protocols (I2C, OneWire, SPI, UART)

from adafruit_esp32spi import adafruit_esp32spi                         # ESP32
from adafruit_esp32spi import adafruit_esp32spi_wifimanager             # ESP32 wifi
import adafruit_esp32spi.adafruit_esp32spi_socket as socket             # ESP32 socket for network

import neopixel                                                         # NeoPixel

from digitalio import DigitalInOut                                      # basic digital IO

import adafruit_adt7410                                                 # temperature sensor

import displayio                                                        # display
import adafruit_touchscreen                                             # touchscreen
from adafruit_bitmap_font import bitmap_font                            # font loading
from adafruit_display_text.label import Label                           # fancy text labels

from adafruit_io.adafruit_io import IO_MQTT, AdafruitIO_RequestError    # adafruit io MQTT
from adafruit_minimqtt import MQTT

# wifi secrets
try:
    from secrets import secrets
except ImportError:
    print("WiFi secrets are kept in secrets.py, please add them there!")
    raise

# hardware (ESP32, neopixel, wifi) setup
# https://docs.espressif.com/projects/esp-idf/en/latest/api-reference/peripherals/spi_master.html
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
status_light = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)
wifi = adafruit_esp32spi_wifimanager.ESPSPI_WiFiManager(esp, secrets, status_light)

# display groups
splash = displayio.Group(max_size=15)
bg_group = displayio.Group(max_size=1)
splash.append(bg_group)

# let there be light
board.DISPLAY.show(splash)

# touchscreen
touchscreen = adafruit_touchscreen.Touchscreen(
    board.TOUCH_XL,
    board.TOUCH_XR,
    board.TOUCH_YD,
    board.TOUCH_YU,
    size=(board.DISPLAY.width, board.DISPLAY.height),
)

# some globals and defaults
global enabled
global EVENT_DURATION
EVENT_DURATION = 5

# font loading
cwd = ("/"+__file__).rsplit('/', 1)[0]
big_font = bitmap_font.load_font(cwd+"/fonts/Nunito-Light-75.bdf")
big_font.load_glyphs(b'0123456789:')

# label positions and colors
minutes_position = (70, 120)
seconds_position = (165, 120)
colon_position = (150, 118)
text_color = 0xFFFFFF

# label groups
text_areas = []
for pos in (minutes_position, seconds_position, colon_position):
    textarea = Label(big_font, text='  ')
    textarea.x = pos[0]
    textarea.y = pos[1]
    textarea.color = text_color
    splash.append(textarea)
    text_areas.append(textarea)
refresh_time = None

# sprite palletes
color_bitmap = displayio.Bitmap(320, 240, 1)
colorp_black = displayio.Palette(1)
colorp_red = displayio.Palette(1)
colorp_black[0] = 0x000000
colorp_red[0] = 0xEF0808

# black background 
bg_black = displayio.TileGrid(color_bitmap,
                               pixel_shader=colorp_black,
                               x=0, y=0)

# red background
bg_red = displayio.TileGrid(color_bitmap,
                               pixel_shader=colorp_red,
                               x=0, y=0)

# Define callback functions which will be called when certain events happen.
# pylint: disable=unused-argument
def connected(client):
    client.subscribe("counter")
    print("listening for counter changes...")

def subscribe(client, userdata, topic, granted_qos):
    print('Subscribed to {0} with QOS level {1}'.format(topic, granted_qos))

def unsubscribe(client, userdata, topic, pid):
    print('Unsubscribed from {0} with PID {1}'.format(topic, pid))

# pylint: disable=unused-argument
def disconnected(client):
    print("Disconnected from Adafruit IO!")

# pylint: disable=unused-argument
def message(client, feed_id, payload):
    global EVENT_DURATION
    print("Feed {0} received new value: {1}".format(feed_id, payload))
    # TODO: protect against NaN
    payload_clean = payload.lstrip('#')
    EVENT_DURATION = int(payload_clean)

# update neopixel using hexadecimal strings (convert to RGB color tuple)
def set_neo_hex(hex):
    payload_clean = hex.lstrip('#')
    color_tuple = tuple(int(payload_clean[i:i+2], 16) for i in (0, 2, 4))
    status_light.fill(color_tuple)

# connect to wifi
wifi.connect()

# initialize MQTT client
mqtt_client = MQTT(
    socket=socket,
    broker="io.adafruit.com",
    username=secrets["aio_username"],
    password=secrets["aio_key"],
    network_manager=wifi
)

# initialize an Adafruit IO MQTT client
io = IO_MQTT(mqtt_client)

# init. adt7410 # temperature sensor for data logging
i2c_bus = busio.I2C(board.SCL, board.SDA)
adt = adafruit_adt7410.ADT7410(i2c_bus, address=0x48)
adt.high_resolution = True

# connect callback methods for adafruit io mqtt
io.on_connect = connected
io.on_disconnect = disconnected
io.on_subscribe = subscribe
io.on_unsubscribe = unsubscribe
io.on_message = message

# connect to adafruits
io.connect()

# set our starting values
minutes = EVENT_DURATION
seconds = 0
enabled = True

# update this guy for fun
set_neo_hex('00FF06')

# counter end function to set background, led, and stop processing of counter
# but we allow the touchscreen to reset everything
def victorypose():
    global enabled
    set_neo_hex('EF0808')
    while bg_group:
        bg_group.pop()
    bg_group.append(bg_red)
    enabled = False

# start our fruityloops
last = 0
last_mqtt = 0

while True:
    # catch touches for reset
    point_being_touched = touchscreen.touch_point
    if point_being_touched:
        minutes = EVENT_DURATION
        seconds = 0
        while bg_group:
            bg_group.pop()
        bg_group.append(bg_black)
        set_neo_hex('000000')
        set_neo_hex('00FF06')
        enabled = True
        continue

    if (time.monotonic() - last) >= 1 and enabled == True:
        last = time.monotonic() # always set this immediately
        set_neo_hex('0D00FF')

        # rollover after one minute
        if seconds < 0:
            seconds = 59
            minutes -= 1

        # TODO: implement negative counter
        if minutes == 0 and seconds == 0:
            victorypose()

        # update our text areas with the new values
        text_areas[0].text = '{:02}'.format(minutes)
        text_areas[1].text = '{:02}'.format(seconds)
        text_areas[2].text = '{:1}'.format(":")

        # increment our second counter
        seconds -= 1

        if enabled != False:
            set_neo_hex('E7FF00')

    if (time.monotonic() - last_mqtt) >= 10:
        last_mqtt = time.monotonic() # always set this immediately
        # wifi handling is built-in, but MQTT connection handling is not
        # lots of errors can happen, but let's just assume the worst and
        # attempt to reconnect

        #temperature = adt.temperature

        try: # adafruit mqtt socket
            io.loop()
        except RuntimeError as e:
            print('connection failure: ', e)
            io.connect()

        # TODO: it seems like to implement something like this, that may
        # take more than 1 second to complete, we need to reconcile our
        # `last` counter for updating the countdown.  I think we should
        # use another? counter that determines the counter decrement by
        # using a diff of this new counter to figure out how many seconds
        # has actually passed to fix whatever the drift is.
        ###
        #try: # wifi connection
        #    try: # send temperature data to IO
        #        temperature = (temperature * 9 / 5) + 32
        #        io.publish("temperature", temperature)
        #    except AdafruitIO_RequestError as e:
        #        print('IO Error: ', e)
        #except (ValueError, RuntimeError) as e: # wifi failure
        #    print("Failed to get data: \n", e)
        #    continue
