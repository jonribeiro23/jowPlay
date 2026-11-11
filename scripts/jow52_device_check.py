"""Validação isolada no aparelho já instalado; não remove arquivos do usuário."""
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

def find(text):
    return lambda ns: next ( (n for n in ns if text.lower() in n.get('text', '').lower()), None)

def initial_screen(ns):
    return next((n for n in ns if n.get('text') in ('Trocar de PC', 'Escolha o PC')), None)

def wait(predicate, label, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            result = predicate(nodes())
            if result is not None and result is not False:
                print('OK:', label, flush=True)
                return result
        except (ET.ParseError, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError('Timeout: ' + label)

def tap(node):
    x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.get('bounds')))
    adb('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2))

def enter(value):
    tap(wait(lambda ns: next((n for n in ns if n.get('class') == 'android.widget.EditText'), None), 'campo'))
    adb('shell', 'input', 'keycombination', 'KEYCODE_CTRL_LEFT', 'KEYCODE_A')
    adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    adb('shell', 'input', 'text', value)
    adb('shell', 'input', 'keyevent', '4')

devices = FakeDevices()
devices.server_id = 'jow52-' + uuid.uuid4().hex
session = SharingSession(devices, failed_attempt_delay=0)
with tempfile.TemporaryDirectory(prefix='jow52-') as temp:
    audio = Path(temp) / ('jow52-' + uuid.uuid4().hex + '.mp3')
    audio.write_bytes(b'ID3' + bytes(4096))
    session.share(audio)
    server = LocalShareServer(session, name='JOW52 teste isolado', http_port=0, discovery_port=0)
    try:
        server.start()
        print('Arquivo de teste:', audio.name, flush=True)
        adb('shell', 'am', 'start', '-n', 'com.ytdown.receiver/.MainActivity')
        time.sleep(2)
        switch = wait(initial_screen, 'tela inicial')
        if switch.get('text') != 'Trocar de PC': switch = None
        if switch is not None: tap(switch)
        enter(f'{local_address()}:{server.port}')
        tap(wait(find('Conectar'), 'conectar'))
        wait(find('Parear com este PC'), 'pareamento')
        enter(session.pairing_code)
        tap(wait(lambda ns: next((n for n in ns if n.get('text') == 'Parear'), None), 'parear'))
        wait(find(audio.stem), 'faixa de teste')
        tap(wait(find('Fazer Download'), 'download disponível'))
        wait(find('Sincronizado'), 'download íntegro sincronizado')
        adb('shell', 'am', 'force-stop', 'com.ytdown.receiver')
        adb('shell', 'am', 'start', '-n', 'com.ytdown.receiver/.MainActivity')
        time.sleep(2)
        switch = wait(initial_screen, 'tela após reabrir')
        if switch.get('text') != 'Trocar de PC': switch = None
        if switch is not None: tap(switch)
        enter(f'{local_address()}:{server.port}')
        tap(wait(find('Conectar'), 'reconectar'))
        wait(find('Sincronizado'), 'associação após reabertura')
        listing = adb('shell', 'ls', '/sdcard/Music/ytDown/' + audio.stem + '-*.mp3').decode().splitlines()
        paths = [p.strip() for p in listing if p.strip().startswith('/sdcard/Music/ytDown/' + audio.stem + '-') and p.strip().endswith('.mp3')]
        if len(paths) != 1:
            raise RuntimeError('Não foi possível identificar exclusivamente o arquivo de teste')
        print('Removendo somente arquivo próprio:', paths[0], flush=True)
        adb('shell', 'rm', paths[0])
        wait(find('Fazer Download'), 'remoção local detectada')
        tap(wait(find('Fazer Download'), 'baixar novamente'))
        wait(find('Sincronizado'), 'novo download sincronizado')
        audio.write_bytes(b'ID3' + bytes([1]) * 4096)
        wait(find('Fazer Download'), 'alteração da origem detectada')
        screenshot = Path(temp) / 'screen.png'
        screenshot.write_bytes(adb('exec-out', 'screencap', '-p'))
        print('Screenshot exec-out obtida em diretório temporário próprio:', screenshot.stat().st_size, 'bytes', flush=True)
    finally:
        server.stop()
