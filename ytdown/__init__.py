"""ytDown: extrai o áudio de vídeos do YouTube e envia para o celular pela rede local.

Camadas (as de dentro não conhecem as de fora):
- domain: conceitos e regras puras, sem bibliotecas externas.
- application: casos de uso e as interfaces (ports) de que eles precisam.
- infrastructure: implementações dessas interfaces (yt-dlp, ffmpeg, mutagen, Pillow, rede).
- presentation: janelas Tkinter e textos mostrados ao usuário.
- main: monta e conecta tudo.
"""
