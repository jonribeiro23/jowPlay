# ytDown

Aplicativo para Windows 10 e 11 que extrai o áudio de um vídeo do YouTube e o salva no computador.

## Como usar

1. Abra `dist\ytDown\ytDown.exe`.
2. Cole a URL do vídeo. Para extrair vários de uma vez, coloque uma URL por linha.
3. Escolha o formato (MP3, M4A, FLAC ou WAV) e a pasta de destino.
4. Clique em **Extrair áudio**.

O arquivo recebe o título do vídeo. Se já existir um arquivo com esse nome, o novo será salvo como `Título (1).mp3`, sem substituir o anterior.

### Vários vídeos de uma vez

Coloque uma URL por linha na caixa de URLs; o botão **Colar** acrescenta o que está na área de transferência ao fim da lista. Enter pula de linha, e **Ctrl+Enter** inicia a extração.

- Os vídeos são extraídos um de cada vez, na ordem da lista. Linhas em branco e URLs repetidas são ignoradas.
- Se algum vídeo falhar, os outros continuam. A lista mostra a situação de cada vídeo, e o resumo no fim explica cada falha.
- **Cancelar** interrompe o vídeo atual e os que ainda não começaram. Os áudios já salvos continuam na pasta.
- Com mais de um vídeo, o campo **Nome** fica desativado e cada áudio recebe o título do próprio vídeo. **Autor** e **Imagem de capa** valem para todos, o que é útil para um álbum.
- **Enviar para o celular** envia todos os áudios salvos da última extração.

### Nome, autor e capa

Estas informações são gravadas no arquivo de áudio para aparecerem nos players. Todas são opcionais:

| Campo | Se ficar vazio |
| --- | --- |
| Nome | Título do vídeo |
| Autor | Fica sem autor |
| Imagem de capa | Imagem padrão (`assets\default_cover.jpg`) |

A capa pode ser JPG, PNG, WebP, BMP ou GIF. Ela é salva em JPEG, com no máximo 1000 pixels no lado maior, e a proporção é mantida. Áreas transparentes ficam brancas.

Depois de cada extração concluída, esses três campos são limpos para que os dados de um áudio não passem para o próximo sem querer.

Os metadados não mudam o nome do arquivo, que continua sendo o título do vídeo. O formato WAV não tem um padrão oficial para capa e autor: o app grava esses dados, mas nem todo player os exibe. Para garantir a exibição, prefira MP3, M4A ou FLAC.

Para trocar a capa padrão, substitua `assets\default_cover.jpg` e gere o aplicativo de novo.

### Enviar para o celular

O app para Android recebe os áudios pela rede local, sem cabo e sem internet.

1. Instale `dist\ytDown-celular.apk` no celular (Android 10 ou mais recente). Pelo cabo, com a depuração USB ativa: `adb install -r dist\ytDown-celular.apk`. Em celulares Xiaomi, ligue também **Instalar via USB** nas opções do desenvolvedor e confirme o aviso que aparece na tela.
2. Conecte o celular ao Wi-Fi da mesma rede do PC.
3. No PC, extraia um áudio e clique em **Enviar para o celular**. Se o Windows perguntar, permita o acesso em redes privadas.
4. Abra o app no celular e escolha o PC. Na primeira vez, digite o código de 6 dígitos mostrado na janela do PC.
5. Toque em **Baixar**. O áudio fica em `Música/ytDown`, com nome, autor e capa, e aparece nos players do celular.

Com a janela "Enviar para o celular" aberta, você pode continuar extraindo: cada novo áudio enviado entra na lista. O compartilhamento termina quando essa janela é fechada.

Se o celular não encontrar o PC, digite no app o endereço mostrado nessa janela. Alguns roteadores bloqueiam a comunicação entre aparelhos; nesse caso, desative o "isolamento de AP" (ou "isolamento de clientes") no roteador, ou use uma rede que não seja a de convidados.

**Segurança:** o celular só consegue baixar os áudios que você enviou, nunca outros arquivos do PC, e só depois de parear. Porém, a transferência não é criptografada: em uma rede que você não controla, outra pessoa poderia ver os áudios enviados. Use em redes de confiança. Para desfazer todos os pareamentos, apague `%APPDATA%\ytDown\pairing.json` com o ytDown fechado.

### Links aceitos

Links de playlist, de canal e de transmissões ao vivo são recusados. Se a URL de um vídeo também tiver um parâmetro de playlist (`&list=...`), apenas esse vídeo é extraído.

## Levar para outro computador

Copie a pasta `dist\ytDown` **inteira**. O `ytDown.exe` não funciona sem a pasta `_internal` ao lado dele. Não é preciso instalar Python nem ffmpeg.

Como o executável não tem assinatura digital, o Windows SmartScreen pode exibir um aviso na primeira execução em outro computador.

## Quando parar de funcionar

O YouTube muda com frequência, e isso pode quebrar o `yt-dlp`. Se os downloads começarem a falhar, gere o aplicativo de novo; o script instala a versão mais recente:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

O script precisa de Python 3 e do ffmpeg instalados (`winget install Gyan.FFmpeg`).

Se o Node.js ou o Deno estiver instalado, o `yt-dlp` pode usá-lo para lidar com as proteções do YouTube. O aplicativo também funcionou sem eles nos testes, mas alguns vídeos podem precisar de um desses programas.

## Desenvolvimento

A versão 2.0 (player e biblioteca, em Qt) está em construção na branch `develop`; o plano está em `docs/arquitetura-2.0.md`. A extração já está na página "Extrair" da interface Qt. Enquanto o envio para o celular não migra (JOW-17), `main.py --legacy` abre a interface Tkinter da versão 1.x.

```powershell
.\.venv\Scripts\python.exe main.py                                  # executa sem empacotar (interface Qt)
.\.venv\Scripts\python.exe main.py --legacy                         # interface Tkinter da 1.x
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .       # testes (não usam a rede)
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1  # gera dist\ytDown
powershell -ExecutionPolicy Bypass -File scripts\build_android.ps1  # gera dist\ytDown-celular.apk
```

O app para Android precisa do JDK 17 e do Android SDK em `%LOCALAPPDATA%\Android`.

### Arquitetura

O código segue a Clean Architecture: está dividido em camadas, e cada camada só depende das que estão mais para dentro. As regras de negócio não conhecem yt-dlp, mutagen, Tkinter nem a rede, e por isso podem ser testadas sem eles. O teste `tests/unit/test_architecture.py` falha se alguma camada importar o que não deve.

```
main.py                    ponto de entrada (também usado pelo PyInstaller)
ytdown/
  domain/                  conceitos e regras puras: formatos, metadados, URLs, erros
  application/             casos de uso (ExtractAudio, ExtractBatch, SharingSession)
    ports.py               interfaces de que os casos de uso precisam
  infrastructure/          implementações dessas interfaces
    youtube.py             download e conversão (yt-dlp + ffmpeg)
    tags.py, covers.py     nome, autor e capa (mutagen + Pillow)
    sharing/               servidor HTTP/UDP para o celular e celulares pareados
  presentation/            todos os textos mostrados ao usuário e as janelas
    qt/                    interface 2.0 em Qt (PySide6): janela principal, navegação, controles
    main_window.py, ...    interface Tkinter da 1.x (sai na JOW-21)
  bootstrap.py             escolhe as implementações e conecta as camadas
tests/
  unit/                    regras e casos de uso, com dublês das interfaces (tests/fakes.py)
  integration/             implementações reais: arquivos de áudio, sockets, janela Tk
  contracts/               baterias que toda implementação de um port precisa passar
assets/                    ícone e capa padrão
scripts/                   scripts de build
android/                   app para Android
```

O app para Android segue a mesma ideia, em `android/app/src/main/java/com/ytdown/receiver/`:

- `domain/`: modelos, regras dos nomes de arquivo, interfaces (`Ports.kt`) e o caso de uso `DownloadAudio`.
- `data/`: descoberta por UDP, cliente HTTP, gravação em Música/ytDown e tokens de pareamento.
- `ui/`: ViewModel, uma tela por arquivo e o tema.
- `AppContainer.kt`: escolhe as implementações e as entrega ao ViewModel.

Para adicionar uma funcionalidade, comece pelo caso de uso em `application` (ou em `domain/usecase` no Android). Se ele precisar de algo externo, declare uma interface em `ports`, implemente em `infrastructure` (ou `data`) e conecte em `bootstrap.py` (ou `AppContainer.kt`).

O APK é assinado com a chave de depuração deste computador. Isso basta para uso pessoal, mas não serve para publicar em lojas de aplicativos, e um APK gerado em outro computador não instala por cima deste sem desinstalar antes.

### Protocolo entre o PC e o celular

- Descoberta: o celular envia `YTDOWN_DISCOVER_V1` em broadcast UDP para a porta 47820, e o PC responde com seu nome, identificador e porta.
- `GET /api/info`: identifica o PC.
- `POST /api/pair`: troca o código de pareamento por um token.
- `GET /api/files`: lista os áudios compartilhados (exige o token).
- `GET /api/files/<id>`: baixa um áudio (exige o token).

O HTTP usa a porta 47821. O código muda após cada pareamento e após 5 tentativas erradas.

## Publicar uma nova versão

O app pronto não fica no repositório (o `ffmpeg.exe` tem mais de 100 MB). Ele é publicado como anexo de um Release do GitHub:

1. Feche o ytDown e gere o app: `scripts\build_windows.ps1` e, se o app do celular mudou, `scripts\build_android.ps1`.
2. Compacte: `Compress-Archive dist\ytDown dist\ytDown-windows.zip -Force`.
3. Publique: `gh release create vX.Y dist\ytDown-windows.zip dist\ytDown-celular.apk --title "ytDown X.Y"`.

## Licenças de terceiros

O app inclui o [FFmpeg](https://ffmpeg.org), em uma versão compilada por [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) e licenciada sob a GPLv3. O `scripts\build_windows.ps1` copia para `dist\ytDown\licencas\ffmpeg` a licença e o `README.txt` dessa versão, que indicam o código-fonte exato utilizado. Quem distribuir o app deve manter essa pasta junto.

Também são usados [yt-dlp](https://github.com/yt-dlp/yt-dlp) (Unlicense), [mutagen](https://github.com/quodlibet/mutagen) (GPLv2+), [Pillow](https://python-pillow.org) (licença MIT-CMU) e Python (licença PSF).

## Uso responsável

Baixe apenas conteúdo que você tem direito de usar. Os Termos de Serviço do YouTube e as leis de direitos autorais continuam valendo.
