"""Teste físico isolado da galeria; não limpa dados nem remove arquivos do aparelho."""
import io
import os
import re
import subprocess
import tempfile
import time
import uuid
import wave
import xml.etree.ElementTree as ET
from pathlib import Path

from mutagen.id3 import APIC, TIT2, TPE1
from mutagen.wave import WAVE
from PIL import Image, ImageDraw
from tests.fakes import FakeDevices
from ytdown.application.sharing import SharingSession
from ytdown.infrastructure.sharing.server import LocalShareServer, local_address

ADB = str(Path(os.environ['LOCALAPPDATA']) / 'Android/Sdk/platform-tools/adb.exe')
ARTIFACTS = Path('docs/evidencias/jow54')
ARTIFACTS.mkdir(parents=True, exist_ok=True)
run_id = uuid.uuid4().hex[:8]

def adb(*args):
    return subprocess.run([ADB, *args], capture_output=True, check=True).stdout

def nodes():
    raw = adb('exec-out', 'uiautomator', 'dump', '/dev/tty')
    return list(ET.fromstring(raw[raw.index(b'<'):raw.rindex(b'>') + 1]).iter('node'))

def find(value):
    return lambda ns: next((n for n in ns if value.lower() in (n.get('text', '') + ' ' + n.get('content-desc', '')).lower()), None)

def wait(predicate, label, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = predicate(nodes())
            if result is not None and result is not False:
                print('OK:', label, flush=True)
                return result
        except (ValueError, ET.ParseError):
            pass
        time.sleep(1)
    raise RuntimeError('Timeout: ' + label)

def tap(node):
    a, b, c, d = map(int, re.findall(r'\d+', node.get('bounds')))
    adb('shell', 'input', 'tap', str((a+c)//2), str((b+d)//2))

def enter(value):
    field = wait(lambda ns: next((n for n in ns if n.get('class') == 'android.widget.EditText'), None), 'campo')
    tap(field)
    adb('shell', 'input', 'keycombination', 'KEYCODE_CTRL_LEFT', 'KEYCODE_A')
    adb('shell', 'input', 'keyevent', 'KEYCODE_DEL')
    adb('shell', 'input', 'text', value)
    adb('shell', 'input', 'keyevent', '4')

def evidence(name):
    (ARTIFACTS / f'{run_id}-{name}.png').write_bytes(adb('exec-out', 'screencap', '-p'))
    raw = adb('exec-out', 'uiautomator', 'dump', '/dev/tty')
    (ARTIFACTS / f'{run_id}-{name}.xml').write_bytes(raw[raw.index(b'<'):raw.rindex(b'>') + 1])
    print('EVIDENCIA:', name, flush=True)

devices = FakeDevices()
devices.server_id = 'jow54-' + run_id
session = SharingSession(devices, failed_attempt_delay=0)
server = None
with tempfile.TemporaryDirectory(prefix='jow54-') as temp:
    for i in range(18):
        path = Path(temp) / f'jow54-{run_id}-{i:02}.wav'
        with wave.open(str(path), 'wb') as audio:
            audio.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            audio.writeframes(bytes(16000))
        tags = WAVE(path)
        tags.add_tags()
        title = f'JOW54 Faixa {i:02}' + (' titulo longo para verificar truncamento na galeria' if i == 0 else '')
        tags.tags.add(TIT2(encoding=3, text=title))
        tags.tags.add(TPE1(encoding=3, text=f'Artista teste {i:02}'))
        if i != 1:
            im = Image.new('RGB', (300, 300), (30 + i * 9, 80, 160))
            ImageDraw.Draw(im).text((40, 130), f'JOW54 {i:02}', fill='white')
            buf = io.BytesIO(); im.save(buf, format='JPEG')
            tags.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='', data=buf.getvalue()))
        tags.save()
        session.share(path)
    try:
        server = LocalShareServer(session, name='JOW54 teste ' + run_id, http_port=0, discovery_port=0)
        server.start(); port = server.port
        print('SERVIDOR:', devices.server_id, local_address(), port, flush=True)
        current = nodes()
        switch = find('Trocar de PC')(current)
        if switch is not None:
            tap(switch); wait(find('Escolha o PC'), 'busca')
        enter(f'{local_address()}:{port}')
        tap(wait(find('Conectar'), 'conectar'))
        wait(find('Parear com este PC'), 'pareamento')
        enter(session.pairing_code)
        tap(wait(lambda ns: next((n for n in ns if n.get('text') == 'Parear'), None), 'parear'))
        wait(find('JOW54 Faixa 00'), 'catálogo sintético')
        time.sleep(3); evidence('galeria')
        tap(wait(find('JOW54 Faixa 00'), 'capa para download'))
        wait(find('Sincronizado'), 'download sincronizado', timeout=60)
        evidence('sincronizado')
        for _ in range(5):
            adb('shell', 'input', 'swipe', '1000', '850', '1000', '350', '450')
            if find('JOW54 Faixa 17')(nodes()) is not None:
                break
        wait(find('JOW54 Faixa 17'), 'rolagem até final', timeout=15)
        evidence('rolagem')
        server.stop(); server = None
        wait(find('Sem conexão'), 'desconexão')
        evidence('desconectado')
        server = LocalShareServer(session, name='JOW54 teste ' + run_id, http_port=port, discovery_port=0)
        server.start()
        wait(lambda ns: find('JOW54 Faixa')(ns) is not None and find('Sem conexão')(ns) is None, 'reconexão sem navegar', timeout=60)
        time.sleep(3); evidence('reconectado')
        print('CONCLUIDO:', run_id, flush=True)
    finally:
        if server: server.stop()
