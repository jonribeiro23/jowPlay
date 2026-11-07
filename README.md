# ytDown

Aplicativo para Windows 10 e 11 que extrai o áudio de um vídeo do YouTube e o salva no computador.

## Como usar

1. Abra `dist\ytDown\ytDown.exe`.
2. Cole a URL do vídeo.
3. Escolha o formato (MP3, M4A, FLAC ou WAV) e a pasta de destino.
4. Clique em **Extrair áudio**.

O arquivo recebe o título do vídeo. Se já existir um arquivo com esse nome, o novo será salvo como `Título (1).mp3`, sem substituir o anterior.

### Nome, autor e capa

Estas informações são gravadas no arquivo de áudio para aparecerem nos players. Todas são opcionais:

| Campo | Se ficar vazio |
| --- | --- |
| Nome | Título do vídeo |
| Autor | Fica sem autor |
| Imagem de capa | Imagem padrão (`default_cover.jpg`) |

A capa pode ser JPG, PNG, WebP, BMP ou GIF. Ela é salva em JPEG, com no máximo 1000 pixels no lado maior, e a proporção é mantida. Áreas transparentes ficam brancas.

Depois de cada extração concluída, esses três campos são limpos para que os dados de um áudio não passem para o próximo sem querer.

Os metadados não mudam o nome do arquivo, que continua sendo o título do vídeo. O formato WAV não tem um padrão oficial para capa e autor: o app grava esses dados, mas nem todo player os exibe. Para garantir a exibição, prefira MP3, M4A ou FLAC.

Para trocar a capa padrão, substitua `default_cover.jpg` e gere o aplicativo de novo.

### Links aceitos

Links de playlist, de canal e de transmissões ao vivo são recusados. Se a URL de um vídeo também tiver um parâmetro de playlist (`&list=...`), apenas esse vídeo é extraído.

## Levar para outro computador

Copie a pasta `dist\ytDown` **inteira**. O `ytDown.exe` não funciona sem a pasta `_internal` ao lado dele. Não é preciso instalar Python nem ffmpeg.

Como o executável não tem assinatura digital, o Windows SmartScreen pode exibir um aviso na primeira execução em outro computador.

## Quando parar de funcionar

O YouTube muda com frequência, e isso pode quebrar o `yt-dlp`. Se os downloads começarem a falhar, gere o aplicativo de novo; o script instala a versão mais recente:

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

O script precisa de Python 3 e do ffmpeg instalados (`winget install Gyan.FFmpeg`).

Se o Node.js ou o Deno estiver instalado, o `yt-dlp` pode usá-lo para lidar com as proteções do YouTube. O aplicativo também funcionou sem eles nos testes, mas alguns vídeos podem precisar de um desses programas.

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe app.py          # executa sem empacotar
.\.venv\Scripts\python.exe -m unittest     # testes (não usam a rede)
```

- `core.py`: download e conversão, com `yt-dlp` e `ffmpeg`.
- `tags.py`: nome, autor e capa do arquivo de áudio, com `mutagen` e Pillow.
- `app.py`: interface gráfica, com Tkinter.
- `build.ps1`: gera o executável, com PyInstaller.

## Uso responsável

Baixe apenas conteúdo que você tem direito de usar. Os Termos de Serviço do YouTube e as leis de direitos autorais continuam valendo.
