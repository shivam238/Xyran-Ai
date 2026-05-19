import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import os
import shutil

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

loop = GLib.MainLoop()
screenshot_path = None

def response_handler(response, results):
    global screenshot_path
    if response == 0:
        uri = results.get('uri', '')
        local_path = uri.replace('file://', '')
        dest = '/tmp/xyran_screen.png'
        shutil.copy(local_path, dest)
        screenshot_path = dest
        print(f"Screenshot liya: {dest}")
    else:
        print("Screenshot cancel ya fail hua")
    loop.quit()

bus = dbus.SessionBus()
portal = bus.get_object(
    'org.freedesktop.portal.Desktop',
    '/org/freedesktop/portal/desktop'
)
screenshot_iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')

import random, string
token = ''.join(random.choices(string.ascii_lowercase, k=8))
sender = bus.get_unique_name().replace('.', '_').replace(':', '')
request_path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'

request_obj = bus.get_object('org.freedesktop.portal.Desktop', request_path)
request_iface = dbus.Interface(request_obj, 'org.freedesktop.portal.Request')
request_iface.connect_to_signal('Response', response_handler)

options = dbus.Dictionary({
    'handle_token': dbus.String(token),
    'interactive': dbus.Boolean(False)
}, signature='sv')

screenshot_iface.Screenshot('', options)
print("Screenshot request bheji — dialog aayega screen pe, Allow karo...")
loop.run()
