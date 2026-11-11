import os
import re
import subprocess
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from tests.fakes import FakeDevices
from ytdown.application.sharing import SharingSession
from ytdown.infrastructure.sharing.server import LocalShareServer, local_address

ADB = str(Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk/platform-tools/adb.exe')

def adb(*args):
    return subprocess.run([ADB, *args], capture_output=True, check=True).stdout

def nodes():
    raw = adb('exec-out', 'uiautomator', 'dump', '/dev/tty')
    return list(ET.fromstring(raw[raw.index(b'<'):raw.rindex(b'>') + 1]).iter('node'))

def wait_for(predicate, description, timeout=35):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            result = predicate(nodes())
            if result is not None and result is not False:
                print('OK:', description, flush=True)
                return result
        except (ET.ParseError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('Timeout: ' + description)

def text_contains(value):
    return lambda ns: next((n for n in ns if value.lower() in n.get('text', '').lower()), None)

def tap(node):
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
    adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))

def field(ns):
    return next((n for n in ns if n.get('class') == 'android.widget.EditText'), None)

def enter(value):
    tap(wait_for(field, 'campo disponível'))
    adb('shell', 'input', 'keycombination', 'KEYCODE_CTRL_LEFT', 'KEYCODE_A')
    adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    adb('shell', 'input', 'text', value)
    adb('shell', 'input', 'keyevent', '4')

def connect(address):
    enter(address)
    tap(wait_for(text_contains('Conectar'), 'botão conectar'))

devices = FakeDevices()
devices.server_id = 'jow50-' + uuid.uuid4().hex
session = SharingSession(devices, failed_attempt_delay=0)
server = None
with tempfile.TemporaryDirectory(prefix='jow50-') as temp:
    audio = Path(temp) / ('jow50-' + uuid.uuid4().hex + '.mp3')
    audio.write_bytes(b'ID3' + bytes(4096))
    session.share(audio)
    try:
        server = LocalShareServer(session, name='JOW50 teste isolado', http_port=0, discovery_port=0)
        server.start()
        port = server.port
        current = nodes()
        switch = text_contains('Trocar de PC')(current)
        if switch is not None:
            tap(switch)
            wait_for(text_contains('Escolha o PC'), 'busca inicial')
        connect(f'{local_address()}:{port}')
        wait_for(text_contains('Parear com este PC'), 'tela de pareamento')
        enter(session.pairing_code)
        tap(wait_for(lambda ns: next((n for n in ns if n.get('text') == 'Parear'), None), 'botão parear'))
        wait_for(text_contains(audio.name), 'pareamento e lista de teste')
        server.stop()
        server = None
        wait_for(text_contains('Sem conex'), 'perda do servidor')
        server = LocalShareServer(session, name='JOW50 teste isolado', http_port=port, discovery_port=0)
        server.start()
        wait_for(lambda ns: text_contains(audio.name)(ns) is not None and text_contains('Sem conex')(ns) is None, 'restauro sem novo pareamento', 50)
        tap(wait_for(text_contains('Trocar de PC'), 'ação trocar de PC'))
        wait_for(text_contains('Escolha o PC'), 'retorno à busca')
        connect(f'{local_address()}:{port}')
        wait_for(text_contains(audio.name), 'reabertura sem novo pareamento')
        print('VALIDAÇÃO CONCLUÍDA', flush=True)
    finally:
        if server:
            server.stop()
