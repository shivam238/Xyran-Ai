import dbus
import dbus.mainloop.glib
from gi.repository import GLib
import base64
import os
import shutil
import random
import string
from groq import Groq
from config import GROQ_API_KEY

client = Groq(api_key=GROQ_API_KEY)

def take_screenshot():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    result_path = [None]
    error_msg = [None]

    def response_handler(response, results):
        if response == 0:
            uri = results.get('uri', '')
            local_path = uri.replace('file://', '')
            dest = '/tmp/xyran_screen.png'
            shutil.copy(local_path, dest)
            result_path[0] = dest
        else:
            error_msg[0] = "Screenshot cancel ya fail hua"
        loop.quit()

    try:
        bus = dbus.SessionBus()
        portal = bus.get_object(
            'org.freedesktop.portal.Desktop',
            '/org/freedesktop/portal/desktop'
        )
        screenshot_iface = dbus.Interface(portal, 'org.freedesktop.portal.Screenshot')

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

        GLib.timeout_add_seconds(10, loop.quit)
        loop.run()

    except Exception as e:
        return None, str(e)

    return result_path[0], error_msg[0]

def encode_image(path):
    with open(path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")

def analyze_screen(question=None):
    if question is None:
        question = (
            "Look at this screenshot very carefully.\n"
            "IGNORE the left sidebar, dock, launcher, and app icons — those may show installed or pinned apps, not open windows.\n"
            "Never guess a website, tab, app, or file name from icons alone.\n"
            "Start with the frontmost or centered active window first, then mention other visible windows behind it.\n"
            "Focus ONLY on what is actually VISIBLE and OPEN in the main screen content right now:\n"
            "1) Which app window is clearly frontmost and in focus?\n"
            "2) Which other windows are also visible behind or around it?\n"
            "3) If a browser is open, name the visible site/tab ONLY if it is clearly readable.\n"
            "4) If a terminal is open, mention commands/output ONLY if readable.\n"
            "5) If settings, file manager, code editor, or explorer panels are visible, list readable section/file/folder names.\n"
            "6) If anything is blurry or unclear, explicitly say it is not clear instead of guessing.\n"
            "7) What is the user currently doing based only on visible evidence?\n"
            "Be specific, avoid hallucinations, and answer in Hinglish."
        )

    path, error = take_screenshot()
    if error or not path:
        return f"Screenshot nahi le paya: {error}"

    image_data = encode_image(path)

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    },
                    {
                        "type": "text",
                        "text": question
                    }
                ]
            }
        ],
        temperature=0,
        max_tokens=1024
    )

    os.remove(path)
    return response.choices[0].message.content.strip()

if __name__ == "__main__":
    print("Screenshot le raha hoon...")
    result = analyze_screen()
    print(f"\nXyran ki aankhein:\n{result}")
