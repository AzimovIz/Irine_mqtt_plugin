# плагин управления по mqtt

import paho.mqtt.client as ph_mqtt
from vacore import VACore
import os

modname = os.path.basename(__file__)[:-3]

log = {}
max_log_len = 100


def start(core: VACore):
    manifest = {
        "name": "MQTT плагин",
        "version": "1.0",
        "require_online": True,  # При работе в локальной сети онлайн не нужен

        "default_options": {  # Данные для подключения к брокеру mqtt
            "MQTT_CLIENTID": "Irine_voice",
            "MQTT_IP": "example.com",
            "MQTT_USER": "username",
            "MQTT_PASS": "password",
            "MQTT_PORT": 1883,

            "devices": {
                # Список устройств, значение - топик устройства (для лампы будет формироваться так: "/Assistant/u_03")
                'лампу': 'u_01',
            },
        },

        "commands": {  # набор скиллов.
            "включи": mqtt_switch_on,
            "выключи": mqtt_switch_off,
        }
    }
    return manifest


def start_with_options(core: VACore, manifest: dict):  # создаст core.mqtt_clien для отправки данных
    options = manifest["options"]
    core.mqtt_client = ph_mqtt.Client(options["MQTT_CLIENTID"], reconnect_on_failure=True)
    core.mqtt_client.username_pw_set(options["MQTT_USER"], options["MQTT_PASS"])


def check_connection(func):  # при обрыве подключения - переподключиться
    def wrapper(core, *args, **kwargs):
        if not core.mqtt_client.is_connected():
            core.mqtt_client.connect(core.plugin_options(modname)["MQTT_IP"],
                                     core.plugin_options(modname)["MQTT_PORT"])

        return func(core, *args, **kwargs)

    return wrapper


@check_connection
def mqtt_switch_on(core: VACore, phrase: str):  # отправляет "1" в топик названного устройства
    if phrase in core.plugin_options(modname)["devices"]:  # если устройство в списке devices
        topic = f"""cmnd/{core.plugin_options(modname)["devices"][phrase]}/cmnd/Power"""  # формируем путь для публикации
        result = core.mqtt_client.publish(topic, "on")  # публикуем 1 в топик устройства
        if result[0] == 0:
            core.say(f'{phrase} включен')  # сообщение отправлено
        else:
            core.say(f'Ошибка {phrase} не включен')  # сообщение не отправлено
    else:
        core.say(f'Не нашла устройство {phrase}')  # устройства нет в списке devices


@check_connection
def mqtt_switch_off(core: VACore, phrase: str):  # отправляет "0" в топик названного устройства
    if phrase in core.plugin_options(modname)["devices"]:
        topic = topic = f"""cmnd/{core.plugin_options(modname)["devices"][phrase]}/cmnd/Power"""  # формируем путь для публикации
        result = core.mqtt_client.publish(topic, "off")
        if result[0] == 0:
            core.say(f'{phrase} выключен')
        else:
            core.say(f'Ошибка {phrase} не выключен')
    else:
        core.say(f'Не нашла устройство {phrase}')



