import os
import time
import requests
import json
import base64

from dotenv import load_dotenv
from flask import Flask, request, redirect
from flasgger import Swagger, swag_from
from pixoo.pixoo import Channel, Pixoo
from PIL import Image

from swag import definitions
from swag import passthrough

import _helpers

load_dotenv()

pixoo_host = os.environ.get('PIXOO_HOST', 'Pixoo64')
pixoo_screen = int(os.environ.get('PIXOO_SCREEN_SIZE', 64))
pixoo_debug = _helpers.parse_bool_value(os.environ.get('PIXOO_DEBUG', 'false'))

while not _helpers.try_to_request(f'http://{pixoo_host}/get'):
    time.sleep(30)

pixoo = Pixoo(
    pixoo_host,
    pixoo_screen,
    pixoo_debug
)

current_channel = 0

app = Flask(__name__)
app.config['SWAGGER'] = _helpers.get_swagger_config()

swagger = Swagger(app, template=_helpers.get_additional_swagger_template())
definitions.create(swagger)


def _push_immediately(_request):
    if _helpers.parse_bool_value(_request.form.get('push_immediately', default=True)):
        pixoo.push()


@app.route('/', methods=['GET'])
def home():
    return redirect('/apidocs')


@app.route('/brightness/<int:percentage>', methods=['PUT'])
@swag_from('swag/set/brightness.yml')
def brightness(percentage):
    pixoo.set_brightness(percentage)

    return 'OK'

brightness_preset_pos = 0
brightness_presets = [10, 50, 100]
@app.route('/cyclebrightness', methods=['POST'])
def cycle_brightness():
    global brightness_preset_pos
    global brightness_presets
    brightness_preset_pos = (brightness_preset_pos + 1) % len(brightness_presets)
    pixoo.set_brightness(brightness_presets[brightness_preset_pos])
    return 'OK'

@app.route('/cyclechannel', methods=['POST'])
def cycle_channel():
    global current_channel
    current_channel = (current_channel + 1) % 4
    pixoo.set_channel(Channel(current_channel))
    return 'OK'

# Constants
screen_width = 64 - 1
screen_height = 64 - 1

# Preferences # TODO: Some can be request parameters.
slow_load = True
page_pause_seconds = 2
text_color = [255, 255, 255] # white
line_height = 6
character_width = 2
character_spacing = 1
left_margin = 1
top_margin = 1

# Derived values
max_lines_per_page = int(screen_height / line_height)
space_per_char = character_width + 2 * character_spacing
max_chars_per_line = int(screen_width / space_per_char) - 1 # buffer

@app.route('/sentence', methods=['POST'])
@swag_from('swag/ankit/sentence.yml')
def sentence():
    # Make lines.
    print("Splitting into lines.")
    pages = split_into_lines(request.form.get('sentence'))
    print("pages = " + str(pages))
    
    # Pages
    # pages = make_pages(lines, max_lines_per_page)

    page_number = 0
    for page_of_lines in pages:
        line_number = 0

        print("Wiping the screen.")
        pixoo.fill_rgb(0,0,0)

        print("Drawing page #" + str(page_number) + ". Max lines = " + str(max_lines_per_page))
        for line_of_words in page_of_lines:
            # Edge case: Last line, and there's more pages.
            if line_number == max_lines_per_page and page_number < len(pages):
                line_of_words[-1] = "..."
            
            # Text
            line_text = ""
            for word in line_of_words:
                line_text += word + " "

            # Pos
            x = left_margin
            y = top_margin + line_number * line_height

            print("\tdrawing line #" + str(line_number) + ". text = " + line_text)
            pixoo.draw_text_at_location_rgb(
                line_text,
                int(x), int(y),
                int(text_color[0]), int(text_color[1]), int(text_color[2]))

            line_number += 1
            if slow_load:
                pixoo.push()

        # TODO: sleep then draw next page.
        time.sleep(page_pause_seconds)
        pixoo.push()
        page_number += 1
    return 'OK'

def split_into_lines(sentence):
    print("whole sentence = " + sentence)
    # init
    pages = []
    lines = []
    start = 0
    end = 0

    # calc
    all_words = sentence.split()

    # iteration vars
    word_index = 0
    page_index = 0
    remaining_pixels_in_line = 64

    # greedy approach. 
    while (word_index < len(all_words)):
        current_word = all_words[word_index]

        if page_index > 0 and not lines:
            current_word = "..."
            word_index -= 1

        # Edge-case: Too long a word should get hyphenated onto next line
        if (len(current_word) > max_chars_per_line):
            # TODO ---- implement
            line = "hyphenate it if even 1 word won't fit on this line"

        # Make a line.
        # Keep adding words until the line is full.
        words_in_line = []
        remaining_chars = max_chars_per_line
        while (remaining_chars > 0 and len(current_word) < remaining_chars):
            words_in_line.append(current_word)
            word_index += 1
            remaining_chars -= len(current_word)

            if (word_index == len(all_words)):
                break
            current_word = all_words[word_index]

        # Add to lines.
        if words_in_line:
            lines.append(words_in_line)
            print("\t line = " + str(words_in_line))

        # Make a new page
        if len(lines) == max_lines_per_page or word_index >= len(all_words):
            if (word_index < len(all_words)): # More pages remaining 
                # Ellipsis. Last word of last line.
                lines[-1][-1] = "..."
                word_index -= 1
            
            print("New page")
            pages.append(lines)
            page_index += 1
            lines = []

    return pages

# Utils
def make_pages(lines, max_lines_per_page):
    max_lines_per_page = max(1, max_lines_per_page)
    return (lines[i:i+max_lines_per_page] for i in range(0, len(lines), max_lines_per_page))

# ------------------------------ Pre-defined APIs

@app.route('/channel/<int:number>', methods=['PUT'])
@app.route('/face/<int:number>', methods=['PUT'])
@app.route('/visualizer/<int:number>', methods=['PUT'])
@app.route('/clock/<int:number>', methods=['PUT'])

@swag_from('swag/set/generic_number.yml')
def generic_set_number(number):
    global current_channel
    if request.path.startswith('/channel/'):
        pixoo.set_channel(Channel(number))
    elif request.path.startswith('/cyclechannels/'):
        current_channel = (current_channel + 1) % 4
        pixoo.set_channel(Channel(current_channel))
    elif request.path.startswith('/face/'):
        pixoo.set_face(number)
    elif request.path.startswith('/visualizer/'):
        pixoo.set_visualizer(number)
    elif request.path.startswith('/clock/'):
        pixoo.set_clock(number)

    return 'OK'


@app.route('/screen/on/<boolean>', methods=['PUT'])
@swag_from('swag/set/generic_boolean.yml')
def generic_set_boolean(boolean):
    if request.path.startswith('/screen/on/'):
        pixoo.set_screen(_helpers.parse_bool_value(boolean))

    return 'OK'


@app.route('/image', methods=['POST'])
@swag_from('swag/draw/image.yml')
def image():
    pixoo.draw_image_at_location(
        Image.open(request.files['image'].stream),
        int(request.form.get('x')),
        int(request.form.get('y'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/text', methods=['POST'])
@swag_from('swag/draw/text.yml')
def text():
    pixoo.draw_text_at_location_rgb(
        request.form.get('text'),
        int(request.form.get('x')),
        int(request.form.get('y')),
        int(request.form.get('r')),
        int(request.form.get('g')),
        int(request.form.get('b'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/fill', methods=['POST'])
@swag_from('swag/draw/fill.yml')
def fill():
    pixoo.fill_rgb(
        int(request.form.get('r')),
        int(request.form.get('g')),
        int(request.form.get('b'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/line', methods=['POST'])
@swag_from('swag/draw/line.yml')
def line():
    pixoo.draw_line_from_start_to_stop_rgb(
        int(request.form.get('start_x')),
        int(request.form.get('start_y')),
        int(request.form.get('stop_x')),
        int(request.form.get('stop_y')),
        int(request.form.get('r')),
        int(request.form.get('g')),
        int(request.form.get('b'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/rectangle', methods=['POST'])
@swag_from('swag/draw/rectangle.yml')
def rectangle():
    pixoo.draw_filled_rectangle_from_top_left_to_bottom_right_rgb(
        int(request.form.get('top_left_x')),
        int(request.form.get('top_left_y')),
        int(request.form.get('bottom_right_x')),
        int(request.form.get('bottom_right_y')),
        int(request.form.get('r')),
        int(request.form.get('g')),
        int(request.form.get('b'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/pixel', methods=['POST'])
@swag_from('swag/draw/pixel.yml')
def pixel():
    pixoo.draw_pixel_at_location_rgb(
        int(request.form.get('x')),
        int(request.form.get('y')),
        int(request.form.get('r')),
        int(request.form.get('g')),
        int(request.form.get('b'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/character', methods=['POST'])
@swag_from('swag/draw/character.yml')
def character():
    pixoo.draw_character_at_location_rgb(
        request.form.get('character'),
        int(request.form.get('x')),
        int(request.form.get('y')),
        int(request.form.get('r')),
        int(request.form.get('g')),
        int(request.form.get('b'))
    )

    _push_immediately(request)

    return 'OK'


@app.route('/sendText', methods=['POST'])
@swag_from('swag/send/text.yml')
def send_text():
    pixoo.send_text(
        request.form.get('text'),
        (int(request.form.get('x')), int(request.form.get('y'))),
        (int(request.form.get('r')), int(request.form.get('g')), int(request.form.get('b'))),
        (int(request.form.get('identifier'))),
        (int(request.form.get('font'))),
        (int(request.form.get('width'))),
        (int(request.form.get('movement_speed'))),
        (int(request.form.get('direction')))
    )

    return 'OK'


def _reset_gif():
    return requests.post(f'http://{pixoo.address}/post', json.dumps({
        "Command": "Draw/ResetHttpGifId"
    })).json()


def _send_gif(num, offset, width, speed, data):
    return requests.post(f'http://{pixoo.address}/post', json.dumps({
        "Command": "Draw/SendHttpGif",
        "PicID": 1,
        "PicNum": num,
        "PicOffset": offset,
        "PicWidth": width,
        "PicSpeed": speed,
        "PicData": data
    })).json()


def _handle_gif(gif, speed, skip_first_frame):
    if gif.is_animated:
        _reset_gif()

        for i in range(1 if skip_first_frame else 0, gif.n_frames):
            gif.seek(i)

            if gif.size not in ((16, 16), (32, 32), (64, 64)):
                gif_frame = gif.resize((pixoo.size, pixoo.size)).convert("RGB")
            else:
                gif_frame = gif.convert("RGB")

            _send_gif(
                gif.n_frames + (-1 if skip_first_frame else 0),
                i + (-1 if skip_first_frame else 0),
                gif_frame.width,
                speed,
                base64.b64encode(gif_frame.tobytes()).decode("utf-8")
            )
    else:
        pixoo.draw_image(gif)
        pixoo.push()


@app.route('/sendGif', methods=['POST'])
@swag_from('swag/send/gif.yml')
def send_gif():
    _handle_gif(
        Image.open(request.files['gif'].stream),
        int(request.form.get('speed')),
        _helpers.parse_bool_value(request.form.get('skip_first_frame', default=False))
    )

    return 'OK'


@app.route('/download/gif', methods=['POST'])
@swag_from('swag/download/gif.yml')
def download_gif():
    try:
        response = requests.get(
            request.form.get('url'),
            stream=True,
            timeout=int(request.form.get('timeout')),
            verify=_helpers.parse_bool_value(request.form.get('ssl_verify', default=True))
        )

        response.raise_for_status()

        _handle_gif(
            Image.open(response.raw),
            int(request.form.get('speed')),
            _helpers.parse_bool_value(request.form.get('skip_first_frame', default=False))
        )
    except (requests.exceptions.RequestException, OSError, IOError) as e:
        return f'Error downloading the GIF: {e}', 400

    return 'OK'


@app.route('/download/image', methods=['POST'])
@swag_from('swag/download/image.yml')
def download_image():
    try:
        response = requests.get(
            request.form.get('url'),
            stream=True,
            timeout=int(request.form.get('timeout')),
            verify=_helpers.parse_bool_value(request.form.get('ssl_verify', default=True))
        )

        response.raise_for_status()

        pixoo.draw_image_at_location(
            Image.open(response.raw),
            int(request.form.get('x')),
            int(request.form.get('y'))
        )

        _push_immediately(request)
    except (requests.exceptions.RequestException, OSError, IOError) as e:
        return f'Error downloading the image: {e}', 400

    return 'OK'


passthrough_routes = {
    # channel ...
    '/passthrough/channel/setIndex': passthrough.create(*passthrough.channel_set_index),
    '/passthrough/channel/setCustomPageIndex': passthrough.create(*passthrough.channel_set_custom_page_index),
    '/passthrough/channel/setEqPosition': passthrough.create(*passthrough.channel_set_eq_position),
    '/passthrough/channel/cloudIndex': passthrough.create(*passthrough.channel_cloud_index),
    '/passthrough/channel/getIndex': passthrough.create(*passthrough.channel_get_index),
    '/passthrough/channel/setBrightness': passthrough.create(*passthrough.channel_set_brightness),
    '/passthrough/channel/getAllConf': passthrough.create(*passthrough.channel_get_all_conf),
    '/passthrough/channel/onOffScreen': passthrough.create(*passthrough.channel_on_off_screen),
    # sys ...
    '/passthrough/sys/logAndLat': passthrough.create(*passthrough.sys_log_and_lat),
    '/passthrough/sys/timeZone': passthrough.create(*passthrough.sys_timezone),
    # device ...
    '/passthrough/device/setUTC': passthrough.create(*passthrough.device_set_utc),
    '/passthrough/device/SetScreenRotationAngle': passthrough.create(*passthrough.device_set_screen_rotation_angle),
    '/passthrough/device/SetMirrorMode': passthrough.create(*passthrough.device_set_mirror_mode),
    '/passthrough/device/getDeviceTime': passthrough.create(*passthrough.device_get_device_time),
    '/passthrough/device/setDisTempMode': passthrough.create(*passthrough.device_set_dis_temp_mode),
    '/passthrough/device/setTime24Flag': passthrough.create(*passthrough.device_set_time_24_flag),
    '/passthrough/device/setHighLightMode': passthrough.create(*passthrough.device_set_high_light_mode),
    '/passthrough/device/setWhiteBalance': passthrough.create(*passthrough.device_set_white_balance),
    '/passthrough/device/getWeatherInfo': passthrough.create(*passthrough.device_get_weather_info),
    '/passthrough/device/playBuzzer': passthrough.create(*passthrough.device_play_buzzer),
    # tools ...
    '/passthrough/tools/setTimer': passthrough.create(*passthrough.tools_set_timer),
    '/passthrough/tools/setStopWatch': passthrough.create(*passthrough.tools_set_stop_watch),
    '/passthrough/tools/setScoreBoard': passthrough.create(*passthrough.tools_set_score_board),
    '/passthrough/tools/setNoiseStatus': passthrough.create(*passthrough.tools_set_noise_status),
    # draw ...
    '/passthrough/draw/sendHttpText': passthrough.create(*passthrough.draw_send_http_text),
    '/passthrough/draw/clearHttpText': passthrough.create(*passthrough.draw_clear_http_text),
    '/passthrough/draw/sendHttpGif': passthrough.create(*passthrough.draw_send_http_gif),
    '/passthrough/draw/resetHttpGifId': passthrough.create(*passthrough.draw_reset_http_gif_id),
}


def _passthrough_request(passthrough_request):
    return requests.post(f'http://{pixoo.address}/post', json.dumps(passthrough_request.json)).json()


for _route, _swag in passthrough_routes.items():
    exec(f"""
@app.route('{_route}', methods=['POST'], endpoint='{_route}')
@swag_from({_swag}, endpoint='{_route}')
def passthrough_{list(passthrough_routes.keys()).index(_route)}():
    return _passthrough_request(request)
        """)


@app.route('/divoom/device/lan', methods=['POST'])
@swag_from('swag/divoom/device/return_same_lan_device.yml')
def divoom_return_same_lan_device():
    return _helpers.divoom_api_call('Device/ReturnSameLANDevice').json()


@app.route('/divoom/channel/dial/types', methods=['POST'])
@swag_from('swag/divoom/channel/get_dial_type.yml')
def divoom_get_dial_type():
    return _helpers.divoom_api_call('Channel/GetDialType').json()


@app.route('/divoom/channel/dial/list', methods=['POST'])
@swag_from('swag/divoom/channel/get_dial_list.yml')
def divoom_get_dial_list():
    return _helpers.divoom_api_call(
        'Channel/GetDialList',
        {
            'DialType': request.form.get('dial_type', default='Game'),
            'Page': int(request.form.get('page_number', default='1'))
        }
    ).json()


if __name__ == '__main__':
    print("Starting 🪴")
    app.run(
        debug=_helpers.parse_bool_value(os.environ.get('PIXOO_REST_DEBUG', 'false')),
        host=os.environ.get('PIXOO_REST_HOST', '127.0.0.1'),
        port=os.environ.get('PIXOO_REST_PORT', '5100')
    )
    print("Ran app.run 🪴")
