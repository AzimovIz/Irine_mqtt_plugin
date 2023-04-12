# плагин управления по mqtt

import paho.mqtt.client as ph_mqtt
from vacore import VACore
import os
import json
from pymorphy2 import MorphAnalyzer

modname = os.path.basename(__file__)[:-3]

device_config = "devices.json"


class Sentence:
    """
    Анализ команд управления устройствами во фразе.
    """

    def __init__(self, commands):
        self.commands = commands  # голые данные из файла с действиями/устройствами
        self.analyzer = MorphAnalyzer()
        self.commands_data = None  # обработанные данные слова/топики/данные для топиков
        self.actions_words = None  # триггер-слова для ассистента из файла с действиями/устройствами

    def _check_inner(self, key_word, word_array):  # проверка вхождения слова в массив слов
        normal_key = self.analyzer.parse(key_word)[0].normal_form  # нормализация слова
        normal_words = list([self.analyzer.parse(word)[0].normal_form for word in word_array])  # нормализация массива слов

        return bool(normal_key in normal_words)

    def _get_answer_word(self, raw_word, pre_word=None):
        # преобразует слова для ответа
        # отвечает от женского имени в прошедшем времени
        # для прилагательных передается дополнительное слово (pre_word) к которому относится это прилагательное
        word = self.analyzer.parse(raw_word)[0]
        part_of_speech = str(word.tag).split(",")[0]
        if "INFN" in part_of_speech or "VERB" in part_of_speech:  # глагол
            ans = word.inflect({"perf", "femn", "sing", "past", "indc"})

        elif "NOUN" in part_of_speech:  # существительное
            if (ans := word.inflect({"inan", "sing", "accs"})) is None:
                word = self.analyzer.parse(word=raw_word)
                word = list(filter(lambda x: "inan" in str(x.tag), word))[0]
                ans = word.inflect({"inan", "sing", "accs"})

        elif "ADJF" in part_of_speech:  # прилогательное
            raw_tags = str(self.analyzer.parse(pre_word)[0].tag)
            tags = raw_tags.replace(" ", ",").replace("accs", "ablt").replace("nomn", "ablt").split(",")[2:]
            ans = word.inflect({tag for tag in tags})

        else:  # если слово не определяется - пропускаем его
            ans = ""

        return ans.word

    def _get_word_keys(self, command):  # "парсинг" команды/топика/данных для топика
        rez = []
        for item in command["items"]:
            for parameter in command["parameters"]:
                rez_n = [
                    command["command"],
                    item["word"],
                ]
                answer = [
                    self._get_answer_word(rez_n[0]),
                    self._get_answer_word(rez_n[1])
                ]
                if "addition" in item:
                    rez_n.append(item["addition"].split(" ")[-1])
                    answer.append(item["addition"])

                if "ALL" not in parameter:
                    rez_n.append(parameter["word"])
                    answer.append(self._get_answer_word(rez_n[-1], answer[1]))

                rez.append({
                    "words": rez_n,
                    "topic": item["topic"],
                    "data": parameter["data"] if not "ALL" in parameter else parameter["ALL"],
                    "answer": " ".join([word for word in answer])
                })

        return rez

    def create_trigger_word(self, raw_word):
        # склоняет триггер-слово команды в повелительное наклонение для вызова ассистента
        # включить > включи / открыть > открой
        word = self.analyzer.parse(raw_word)[0]
        part_of_speech = str(word.tag).split(",")[0]
        if "INFN" not in part_of_speech or "VERB" not in part_of_speech:
            word = self.analyzer.parse(raw_word)
            word = list(filter(lambda x: "INFN" in str(x.tag) or "VERB" in str(x.tag), word))[0]

        return word.inflect({"perf", "sing", "impr", "excl"}).word

    def get_trigger_infn(self, raw_word):
        # возвращает инфинитив от триггер-слова команды
        # включи > включить / открой > открыть
        word = self.analyzer.parse(raw_word)[0]
        part_of_speech = str(word.tag).split(",")[0]
        if "INFN" not in part_of_speech or "VERB" not in part_of_speech:
            word = self.analyzer.parse(raw_word)
            word = list(filter(lambda x: "INFN" in str(x.tag) or "VERB" in str(x.tag), word))[0]

        return word.inflect({"INFN","perf","tran"}).word

    def get_command_words(self):  # возвращает слова действия включи/выключи/и т.д. из файла с действиями/устройствами
        if self.actions_words is None:
            self.actions_words = []
            for command in self.commands:
                self.actions_words.append(self.create_trigger_word(command["command"]))

        return self.actions_words

    def get_commands_list(self):  # возвращает обработанные команды из файла с действиями/устройствами
        if self.commands_data is None:
            self.commands_data = []
            for command in self.commands:
                self.commands_data = self.commands_data + self._get_word_keys(command)

        return self.commands_data

    def get_command(self, raw_text: str):  # находит и возвращает команду все слова которой есть в переданной фразе
        word_list = raw_text.split(" ")
        word_list[0] = self.get_trigger_infn(word_list[0])
        for command in self.get_commands_list():
            if all([self._check_inner(w, word_list) for w in command["words"]]):
                return command

        return False


def start(core: VACore):
    manifest = {
        "name": "MQTT плагин",
        "version": "1.1",
        "require_online": True,  # При работе в локальной сети онлайн не нужен

        "default_options": {  # Данные для подключения к брокеру mqtt
            "MQTT_CLIENTID": "Irine_voice",
            "MQTT_IP": "example.com",
            "MQTT_USER": "username",
            "MQTT_PASS": "password",
            "MQTT_PORT": 1883,
        }
    }

    # открываем файл с действиями/устройствами
    with open(f"sm_home/{device_config}", 'r', encoding="utf-8") as fp:
        data = json.load(fp)

    # добавляем ядру экземпляр анализатора фраз
    core.mqtt_sentence = Sentence(data)

    # в манифест добавляем триггер-слова из файла с действиями/устройствами
    manifest["commands"] = {word: (mqtt_find, word) for word in core.mqtt_sentence.get_command_words()}

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
def mqtt_find(core: VACore, phrase: str, command: str = None):
    if command is not None:
        phrase = command + " " + phrase

    if command := core.mqtt_sentence.get_command(phrase):
        core.mqtt_client.publish(command["topic"], command["data"])
        core.say(command["answer"])
    else:
        core.say("Не могу выполнить команду")
